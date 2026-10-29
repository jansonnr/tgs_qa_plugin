from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from zephyr_scale_mcp.apply_executor import execute_plan_operations
from zephyr_scale_mcp.apply_log import ApplyBusy, apply_log_path, hold_apply_lock
from zephyr_scale_mcp.data_policy import (
    DIRECT_HTTP_BOUNDARY,
    LOCAL_STORAGE,
    QaPathError,
    redact_operations,
    resolve_qa_log_dir,
    to_agent,
)
from zephyr_scale_mcp.apply_gate import (
    direct_write_allowed,
    get_apply_token_store,
    write_gate_denied_payload,
)
from zephyr_scale_mcp.plan_rules import (
    PlanRejected,
    adapt_plan,
    expand_folder_scope,
    folder_query,
    match_candidates,
    plan_hash,
    run_log_key,
    sync_folder_index,
    validate_plan,
)
from zephyr_scale_mcp.client import ZephyrClient
from zephyr_scale_mcp.confluence import ConfluenceClient
from zephyr_scale_mcp.config import ConfigError, get_settings, origin_of, update_settings

_zephyr_client: ZephyrClient | None = None
_confluence_client: ConfluenceClient | None = None


def _invalidate_http_clients() -> None:
    global _zephyr_client, _confluence_client
    if _zephyr_client is not None:
        _zephyr_client._http.close()  # noqa: SLF001 — lifecycle MCP-процесса
        _zephyr_client = None
    if _confluence_client is not None:
        _confluence_client._http.close()  # noqa: SLF001
        _confluence_client = None


mcp = MCPServer(
    "zephyr-scale",
    instructions=(
        "MCP-сервер Zephyr Scale Server API (TMS). "
        "Перед вызовами API сохрани токены через set_credentials: bearer_token для Jira/Zephyr, "
        "wiki_bearer_token для Confluence. "
        "По умолчанию: baseUrl=https://track.astral.ru/soft, projectKey=QA, projectId=10104. "
        "Ключи тест-кейсов вида QA-T77, тест-ранов — QA-R1. "
        "Confluence: get_confluence_page по pageId или URL страницы. "
        "Запись тест-кейсов (create/update/delete) только через prepare_apply и apply_plan; "
        "прямые create_test_case, update_test_case и delete_test_case отклоняются. "
        "prepare_apply принимает plan целиком: нерешённый ask, повтор одного ключа Zephyr "
        "и поиск со статусом ошибки или неполного индекса отклоняются. "
        "case_id — внутренний идентификатор черновика, в Zephyr не отправляется."
    ),
)


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _client() -> ZephyrClient:
    global _zephyr_client
    if _zephyr_client is None:
        _zephyr_client = ZephyrClient(get_settings())
    return _zephyr_client


def _confluence() -> ConfluenceClient:
    global _confluence_client
    if _confluence_client is None:
        _confluence_client = ConfluenceClient(get_settings())
    return _confluence_client


def _apply_payload(plan_hash_value: str, run_id: str | None, results: list[dict[str, Any]]) -> dict[str, Any]:
    batch_ok = all(item["status"] in {"success", "skipped"} for item in results)
    return {
        "ok": batch_ok,
        "plan_hash": plan_hash_value,
        "run_id": run_id,
        "log_path": str(apply_log_path(plan_hash_value)),
        "results": results,
    }


def _prepared_plan(plan: dict[str, Any]) -> dict[str, Any]:
    adapted = adapt_plan(plan)
    validate_plan(adapted)
    return adapted


def _plan_target(plan: dict[str, Any]) -> dict[str, str]:
    settings = get_settings()
    project = settings.project_key
    for operation in plan.get("operations") or []:
        if isinstance(operation, dict) and str(operation.get("project_key") or "").strip():
            project = str(operation["project_key"]).strip()
            break
    return {"origin": origin_of(settings.base_url), "project_key": project}


def _execution_plan(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], Path | None]:
    validate_plan(plan)
    workspace: Path | None = None
    if plan.get("qa_root"):
        try:
            workspace = resolve_qa_log_dir(str(plan["qa_root"]))
        except QaPathError as exc:
            raise PlanRejected("QA_PATH", str(exc)) from exc
    return redact_operations(plan), workspace


@dataclass(frozen=True)
class _PlanExecution:
    adapted: dict[str, Any]
    operations: list[dict[str, Any]]
    workspace_log: Path | None
    target: dict[str, str]
    digest: str
    log_key: str


def _plan_execution(plan: dict[str, Any]) -> _PlanExecution:
    adapted = _prepared_plan(plan)
    operations, workspace_log = _execution_plan(adapted)
    target = _plan_target(adapted)
    digest = plan_hash(adapted, target=target)
    log_key = run_log_key(adapted, origin=target["origin"], project_key=target["project_key"])
    return _PlanExecution(
        adapted=adapted,
        operations=operations,
        workspace_log=workspace_log,
        target=target,
        digest=digest,
        log_key=log_key,
    )


def _apply_log_exists(log_key: str, workspace_log: Path | None) -> bool:
    if apply_log_path(log_key).is_file():
        return True
    return workspace_log is not None and apply_log_path(log_key, workspace_log).is_file()


def _apply_busy_payload() -> str:
    return _dumps(
        {
            "ok": False,
            "code": "APPLY_IN_PROGRESS",
            "error": "Этот план уже выполняется в другом чате. Повторная запись не запущена.",
        }
    )


def _run_under_apply_lock(log_key: str, runner: Callable[[], dict[str, Any]]) -> str:
    try:
        with hold_apply_lock(log_key):
            return _call(runner)
    except ApplyBusy:
        return _apply_busy_payload()


def _call(fn, *args, **kwargs) -> str:
    try:
        result = fn(*args, **kwargs)
    except ConfigError as exc:
        return _dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001 — агенту не отдаём сырой текст внешнего API
        return _dumps({"ok": False, "error": type(exc).__name__})
    if isinstance(result, dict):
        result = to_agent(result)
    return _dumps(result)


@mcp.tool(
    title="Сохранить credentials Zephyr",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True),
)
def set_credentials(
    bearer_token: str | None = None,
    wiki_bearer_token: str | None = None,
    base_url: str | None = None,
    project_key: str | None = None,
    project_id: str | None = None,
    wiki_url: str | None = None,
) -> str:
    """Сохранить токены и параметры подключения в локальный конфиг пользователя.

    Файл: %APPDATA%/zephyr-scale-mcp/config.json (Windows).
    bearer_token — для Jira/Zephyr, wiki_bearer_token — для Confluence. Префикс Bearer необязателен.
    base_url по умолчанию https://track.astral.ru/soft, project_key=QA, project_id=10104.
    wiki_url — базовый URL Confluence; если не задан, берётся {base_url}/wiki.
    Передавай только те поля, которые нужно обновить.
    """
    if bearer_token is None and wiki_bearer_token is None and base_url is None and project_key is None and project_id is None and wiki_url is None:
        return _dumps({"ok": False, "error": "Укажи хотя бы один параметр для сохранения."})
    settings = update_settings(
        bearer_token=bearer_token,
        wiki_bearer_token=wiki_bearer_token,
        base_url=base_url,
        project_key=project_key,
        project_id=project_id,
        wiki_url=wiki_url,
    )
    _invalidate_http_clients()
    return _dumps({"ok": True, "saved": settings.masked()})


@mcp.tool(
    title="Показать конфиг Zephyr",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def get_config() -> str:
    """Показать base_url, wiki_url, projectKey, projectId и маскированные токены Jira и Wiki."""
    payload = get_settings().masked()
    payload["write_gate"] = "apply_token"
    payload["direct_write_allowed"] = direct_write_allowed()
    payload["local_storage"] = LOCAL_STORAGE
    payload["direct_http_boundary"] = DIRECT_HTTP_BOUNDARY
    return _dumps(payload)


@mcp.tool(
    title="Подготовить apply (выдать apply_token)",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
)
def prepare_apply(
    plan: dict[str, Any],
    run_id: str | None = None,
    ttl_seconds: int = 900,
) -> str:
    """Выдать одноразовый apply_token на конкретный plan.

    Вызывай только после явного подтверждения пользователем (Apply), не по фразе в чате.
    plan.search_status — ok или ok_with_limited_index. api_error, index_incomplete и cache_stale
    отклоняют весь план. Нерешённый ask и две операции в один test_case_key тоже отклоняют план.
    case_id — внутренний id черновика. Сервер сам считает plan_hash; правка плана делает token недействительным.
    """
    try:
        adapted = _prepared_plan(plan)
        target = _plan_target(adapted)
        digest = plan_hash(adapted, target=target)
        token, expires_at = get_apply_token_store().issue(
            plan_hash=digest,
            run_id=run_id,
            ttl_seconds=ttl_seconds,
        )
        return _dumps(
            {
                "ok": True,
                "apply_token": token,
                "plan_hash": digest,
                "run_id": run_id,
                "expires_at": expires_at,
            }
        )
    except PlanRejected as exc:
        return _dumps({"ok": False, "code": exc.code, "error": exc.message})
    except ConfigError as exc:
        return _dumps({"ok": False, "code": "CONFIG", "error": str(exc)})
    except ValueError as exc:
        return _dumps({"ok": False, "error": str(exc)})


@mcp.tool(
    title="Применить план в Zephyr",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
)
def apply_plan(apply_token: str, plan: dict[str, Any]) -> str:
    """Единственный путь записи тест-кейсов.

    plan — тот же объект, что у prepare_apply. Перед update кейс читается заново:
    если fingerprint не совпал с baseline_fingerprint, строка не пишется (conflict).
    skip не вызывает Zephyr. case_id в API Zephyr не передаётся.
    Журнал пишется после каждой операции. 401 и 403 останавливают пачку.
    Повторный create после unknown не выполняется: вызови resume_apply для продолжения.
    """
    try:
        execution = _plan_execution(plan)
    except PlanRejected as exc:
        return _dumps({"ok": False, "code": exc.code, "error": exc.message})
    except ConfigError as exc:
        return _dumps({"ok": False, "code": "CONFIG", "error": str(exc)})

    def _run() -> dict[str, Any]:
        record = get_apply_token_store().consume(apply_token, plan_hash=execution.digest)
        if record is None:
            return {
                "ok": False,
                "code": "APPLY_TOKEN_INVALID",
                "error": "apply_token недействителен, истёк, уже использован или план изменился после preview.",
            }
        results = execute_plan_operations(
            _client(),
            execution.operations,
            plan_hash=execution.log_key,
            workspace_log_root=execution.workspace_log,
        )
        return _apply_payload(execution.log_key, record.run_id, results)

    return _run_under_apply_lock(execution.log_key, _run)


@mcp.tool(
    title="Продолжить уже подтверждённый apply",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
)
def resume_apply(apply_token: str, plan: dict[str, Any]) -> str:
    """Продолжить план, который уже прошёл apply_plan.

    Успешные операции не повторяются. create со статусом unknown не создаётся снова.
    Нужен тот же apply_token, что после prepare_apply (уже использованный при первом apply_plan).
    """
    try:
        execution = _plan_execution(plan)
    except PlanRejected as exc:
        return _dumps({"ok": False, "code": exc.code, "error": exc.message})
    except ConfigError as exc:
        return _dumps({"ok": False, "code": "CONFIG", "error": str(exc)})
    if not get_apply_token_store().authorize_resume(apply_token, plan_hash=execution.digest):
        return _dumps(
            {
                "ok": False,
                "code": "APPLY_TOKEN_INVALID",
                "error": "resume_apply требует тот же apply_token после успешного apply_plan; токен истёк или план изменился.",
            }
        )
    if not _apply_log_exists(execution.log_key, execution.workspace_log):
        return _dumps(
            {
                "ok": False,
                "code": "APPLY_NOT_STARTED",
                "error": "Для этого запуска нет журнала. Сначала нужен подтверждённый apply_plan.",
            }
        )

    def _run() -> dict[str, Any]:
        results = execute_plan_operations(
            _client(),
            execution.operations,
            plan_hash=execution.log_key,
            workspace_log_root=execution.workspace_log,
        )
        return _apply_payload(execution.log_key, execution.adapted.get("run_id"), results)

    return _run_under_apply_lock(execution.log_key, _run)


@mcp.tool(
    title="Индекс кейсов выбранных папок",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def sync_testcase_index(
    folder_ids: list[str],
    include_subfolders: bool = False,
    project_key: str | None = None,
    max_pages: int = 40,
) -> str:
    """Постранично загрузить краткий индекс кейсов (key, name, labels, objective, precondition).

    Это не поиск по произвольной фразе. search_status=ok только если прочитаны все страницы.
    index_incomplete и api_error нельзя трактовать как отсутствие дублей.
    """
    if not folder_ids:
        return _dumps({"ok": False, "error": "Укажи хотя бы одну папку."})

    def _run() -> dict[str, Any]:
        client = _client()
        settings = get_settings()
        selected_project = project_key or settings.project_key
        scope = list(folder_ids)
        if include_subfolders:
            if selected_project != settings.project_key or not str(settings.project_id or "").strip():
                return {
                    "ok": False,
                    "search_status": "index_incomplete",
                    "complete": False,
                    "items": [],
                    "error": "Нельзя обойти подпапки: id проекта не разрешён для выбранного project_key.",
                }
            tree = client.get_folder_tree(settings.project_id)
            if tree.get("ok") is not True:
                return {
                    "ok": False,
                    "search_status": "api_error",
                    "complete": False,
                    "items": [],
                    "error": tree.get("data") or tree.get("error"),
                }
            scope = expand_folder_scope(tree.get("data"), folder_ids, include_subfolders=True)
        query = folder_query(selected_project, scope)
        indexed = sync_folder_index(
            lambda tql, page_size, start_at: client.search_test_cases(
                query=tql,
                max_results=page_size,
                start_at=start_at,
                project_key=project_key,
            ),
            query=query,
            max_pages=max_pages,
        )
        indexed["folder_ids"] = scope
        indexed["query"] = query
        return indexed

    return _call(_run)


@mcp.tool(
    title="Отобрать похожие кейсы локально",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def match_test_case_candidates(
    index_items: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> str:
    """Сопоставить черновики с уже загруженным индексом.

    cases[].case_id — внутренний id. Высокое совпадение предлагает ask, не update.
    skip предлагается только при confirmed_skip и совпадении шагов.
    Пустой shortlist означает «по доступным полям похожих не найдено», а не «дублей нет».
    """
    return _dumps(match_candidates(index_items, cases))


@mcp.tool(
    title="Создать тест-кейс",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
)
def create_test_case(
    name: str,
    objective: str | None = None,
    folder: str | None = None,
    status: str = "Draft",
    priority: str = "Normal",
    project_key: str | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> str:
    """Создать тест-кейс (POST /rest/atm/1.0/testcase).

    folder — путь вида /Чит-листы. steps — список объектов с полями
    description, test_data (или testData), expected_result (или expectedResult).
    Без apply_token используй apply_plan. Прямой вызов отклоняется (кроме ZEPHYR_ALLOW_DIRECT_WRITE).
    """
    if not direct_write_allowed():
        return _dumps(write_gate_denied_payload())
    return _call(
        _client().create_test_case,
        name=name,
        objective=objective,
        folder=folder,
        status=status,
        priority=priority,
        project_key=project_key,
        steps=steps,
    )


@mcp.tool(
    title="Получить тест-кейс",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def get_test_case(test_case_key: str) -> str:
    """Получить тест-кейс по ключу (GET /rest/atm/1.0/testcase/{key}), например QA-T77."""
    return _call(_client().get_test_case, test_case_key)


@mcp.tool(
    title="Обновить тест-кейс",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True),
)
def update_test_case(
    test_case_key: str,
    name: str | None = None,
    objective: str | None = None,
    folder: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> str:
    """Обновить тест-кейс (PUT /rest/atm/1.0/testcase/{key}). Передавай только поля, которые нужно изменить.

    Без apply_token используй apply_plan. Прямой вызов отклоняется (кроме ZEPHYR_ALLOW_DIRECT_WRITE).
    """
    if not direct_write_allowed():
        return _dumps(write_gate_denied_payload())
    return _call(
        _client().update_test_case,
        test_case_key,
        name=name,
        objective=objective,
        folder=folder,
        status=status,
        priority=priority,
        steps=steps,
    )


@mcp.tool(
    title="Удалить тест-кейс",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
)
def delete_test_case(test_case_key: str) -> str:
    """Удалить тест-кейс (DELETE /rest/atm/1.0/testcase/{key}).

    Без apply_token используй apply_plan. Прямой вызов отклоняется (кроме ZEPHYR_ALLOW_DIRECT_WRITE).
    """
    if not direct_write_allowed():
        return _dumps(write_gate_denied_payload())
    return _call(_client().delete_test_case, test_case_key)


@mcp.tool(
    title="Найти тест-кейсы",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def search_test_cases(
    query: str | None = None,
    max_results: int = 50,
    start_at: int = 0,
    project_key: str | None = None,
) -> str:
    """Поиск тест-кейсов (GET /rest/atm/1.0/testcase/search).

    query — TQL, например projectKey = "QA". Если не задан, ищет по текущему project_key.
    """
    return _call(
        _client().search_test_cases,
        query=query,
        max_results=max_results,
        start_at=start_at,
        project_key=project_key,
    )


@mcp.tool(
    title="Последний результат тест-кейса",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def get_latest_test_result(test_case_key: str) -> str:
    """Последний результат выполнения тест-кейса (GET /rest/atm/1.0/testcase/{key}/testresult/latest)."""
    return _call(_client().get_latest_test_result, test_case_key)


@mcp.tool(
    title="Вложения тест-кейса",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def list_test_case_attachments(test_case_key: str) -> str:
    """Список вложений тест-кейса (GET /rest/atm/1.0/testcase/{key}/attachments)."""
    return _call(_client().list_test_case_attachments, test_case_key)


@mcp.tool(
    title="Загрузить вложение к тест-кейсу",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
)
def upload_test_case_attachment(
    test_case_key: str,
    file_path: str,
    filename: str | None = None,
) -> str:
    """Загрузить файл к тест-кейсу (POST multipart /rest/atm/1.0/testcase/{key}/attachments). file_path — локальный путь.

    Запись к кейсу: без apply_token отклоняется (кроме ZEPHYR_ALLOW_DIRECT_WRITE). Для MVP используй apply_plan.
    """
    if not direct_write_allowed():
        return _dumps(write_gate_denied_payload())
    return _call(
        _client().upload_test_case_attachment,
        test_case_key,
        file_path,
        filename=filename,
    )


@mcp.tool(
    title="Создать тест-ран",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False),
)
def create_test_run(
    name: str,
    folder: str | None = None,
    description: str | None = None,
    test_case_keys: list[str] | None = None,
    project_key: str | None = None,
) -> str:
    """Создать тест-ран / цикл (POST /rest/atm/1.0/testrun). test_case_keys — список ключей, например ["QA-T77","QA-T76"]."""
    if not direct_write_allowed():
        return _dumps(write_gate_denied_payload())
    return _call(
        _client().create_test_run,
        name=name,
        folder=folder,
        description=description,
        test_case_keys=test_case_keys,
        project_key=project_key,
    )


@mcp.tool(
    title="Получить тест-ран",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def get_test_run(test_run_key: str) -> str:
    """Получить тест-ран по ключу (GET /rest/atm/1.0/testrun/{key})."""
    return _call(_client().get_test_run, test_run_key)


@mcp.tool(
    title="Удалить тест-ран",
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
)
def delete_test_run(test_run_key: str) -> str:
    """Удалить тест-ран (DELETE /rest/atm/1.0/testrun/{key})."""
    if not direct_write_allowed():
        return _dumps(write_gate_denied_payload())
    return _call(_client().delete_test_run, test_run_key)


@mcp.tool(
    title="Найти тест-раны",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def search_test_runs(
    query: str | None = None,
    max_results: int = 50,
    project_key: str | None = None,
) -> str:
    """Поиск тест-ранов (GET /rest/atm/1.0/testrun/search). Без query — все раны текущего project_key."""
    return _call(
        _client().search_test_runs,
        query=query,
        max_results=max_results,
        project_key=project_key,
    )


@mcp.tool(
    title="Получить папку",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def get_folder(folder_id: str) -> str:
    """Получить папку по id (GET /rest/tests/1.0/folder/{id})."""
    return _call(_client().get_folder, folder_id)


@mcp.tool(
    title="Дерево папок тест-кейсов",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def get_folder_tree(project_id: str | None = None) -> str:
    """Дерево папок тест-кейсов проекта (GET /rest/tests/1.0/project/{projectId}/foldertree/testcase)."""
    return _call(_client().get_folder_tree, project_id)


@mcp.tool(
    title="Получить страницу Confluence",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
def get_confluence_page(
    page_id_or_url: str,
    include_linked_pages: bool = False,
    text_offset: int = 0,
) -> str:
    """Прочитать страницу Confluence и вернуть Markdown.

    page_id_or_url — числовой pageId или URL вида
    https://.../pages/viewpage.action?pageId=123456.
    include_linked_pages=true подгружает страницы, на которые есть ссылки внутри текста.
    text_offset — продолжение усечённого текста. content_complete=false значит, что страница прочитана не до конца.
    Использует GET /rest/api/content/{pageId}?expand=body.storage.
    """
    max_depth = 1 if include_linked_pages else 0
    return _call(_confluence().get_page, page_id_or_url, max_depth=max_depth, text_offset=text_offset)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
