from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


ENV_BASE_URL = "ZEPHYR_BASE_URL"
ENV_TOKEN = "ZEPHYR_BEARER_TOKEN"
ENV_WIKI_TOKEN = "ZEPHYR_WIKI_BEARER_TOKEN"
ENV_PROJECT_KEY = "ZEPHYR_PROJECT_KEY"
ENV_PROJECT_ID = "ZEPHYR_PROJECT_ID"
ENV_WIKI_URL = "ZEPHYR_WIKI_URL"
ENV_TRUSTED_ORIGINS = "ZEPHYR_TRUSTED_ORIGINS"

DEFAULT_BASE_URL = "https://track.astral.ru/soft"
DEFAULT_PROJECT_KEY = "QA"
DEFAULT_PROJECT_ID = "10104"


class ConfigError(RuntimeError):
    """Ошибка конфигурации (нет токена, битый файл и т.п.)."""


def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "zephyr-scale-mcp"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "zephyr-scale-mcp"
    return Path.home() / ".config" / "zephyr-scale-mcp"


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class Settings:
    base_url: str = DEFAULT_BASE_URL
    bearer_token: str = ""
    wiki_bearer_token: str = ""
    project_key: str = DEFAULT_PROJECT_KEY
    project_id: str = DEFAULT_PROJECT_ID
    wiki_url: str = ""

    def wiki_url_resolved(self) -> str:
        explicit = (self.wiki_url or "").strip().rstrip("/")
        if explicit:
            return explicit
        return f"{self.base_url.rstrip('/')}/wiki"

    @staticmethod
    def _format_auth_header(token: str, *, env_name: str) -> str:
        value = (token or "").strip()
        if not value:
            raise ConfigError(
                f"Bearer-токен не задан ({env_name}). Вызови set_credentials "
                f"или положи токен в {config_path()}."
            )
        if value.lower().startswith("bearer "):
            return value
        return f"Bearer {value}"

    def auth_header(self) -> str:
        return self._format_auth_header(self.bearer_token, env_name=ENV_TOKEN)

    def wiki_auth_header(self) -> str:
        return self._format_auth_header(self.wiki_bearer_token, env_name=ENV_WIKI_TOKEN)

    @staticmethod
    def _mask_token(token: str) -> str:
        tok = token or ""
        if not tok:
            return ""
        if len(tok) <= 8:
            return "****"
        return f"{tok[:4]}...{tok[-4:]}"

    def masked(self) -> dict[str, object]:
        return {
            "base_url": self.base_url,
            "bearer_token": self._mask_token(self.bearer_token),
            "token_set": bool(self.bearer_token),
            "wiki_bearer_token": self._mask_token(self.wiki_bearer_token),
            "wiki_token_set": bool(self.wiki_bearer_token),
            "project_key": self.project_key,
            "project_id": self.project_id,
            "wiki_url": self.wiki_url_resolved(),
            "config_path": str(config_path()),
        }


_runtime: Settings | None = None


def _read_file() -> dict[str, str]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Некорректный JSON в {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} должен содержать JSON-объект")
    return {str(k): "" if v is None else str(v) for k, v in data.items()}


def _write_file(settings: Settings) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_settings() -> Settings:
    file_data = _read_file()
    return Settings(
        base_url=_first_nonempty(
            os.environ.get(ENV_BASE_URL),
            file_data.get("base_url"),
            DEFAULT_BASE_URL,
        ),
        bearer_token=_first_nonempty(
            os.environ.get(ENV_TOKEN),
            file_data.get("bearer_token"),
            "",
        ),
        wiki_bearer_token=_first_nonempty(
            os.environ.get(ENV_WIKI_TOKEN),
            file_data.get("wiki_bearer_token"),
            "",
        ),
        project_key=_first_nonempty(
            os.environ.get(ENV_PROJECT_KEY),
            file_data.get("project_key"),
            DEFAULT_PROJECT_KEY,
        ),
        project_id=_first_nonempty(
            os.environ.get(ENV_PROJECT_ID),
            file_data.get("project_id"),
            DEFAULT_PROJECT_ID,
        ),
        wiki_url=_first_nonempty(
            os.environ.get(ENV_WIKI_URL),
            file_data.get("wiki_url"),
            "",
        ),
    )


def get_settings() -> Settings:
    global _runtime
    if _runtime is None:
        _runtime = load_settings()
    return _runtime


def origin_of(url: str) -> str:
    """https-origin без пути. http, логин, query и fragment отклоняются."""
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or not parts.hostname:
        raise ConfigError("Адрес подключения должен быть https и содержать хост.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ConfigError("В адресе не допускаются логин, query и fragment.")
    host = parts.hostname.lower()
    if parts.port:
        host = f"{host}:{parts.port}"
    return f"https://{host}"


def trusted_origins() -> set[str]:
    """Список задаётся окружением, не аргументом tool."""
    raw = os.environ.get(ENV_TRUSTED_ORIGINS) or ""
    found: set[str] = set()
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        found.add(origin_of(text))
    return found


def update_settings(
    *,
    bearer_token: str | None = None,
    wiki_bearer_token: str | None = None,
    base_url: str | None = None,
    project_key: str | None = None,
    project_id: str | None = None,
    wiki_url: str | None = None,
) -> Settings:
    settings = get_settings()
    if bearer_token is not None:
        settings.bearer_token = bearer_token.strip()
    if wiki_bearer_token is not None:
        settings.wiki_bearer_token = wiki_bearer_token.strip()
    if base_url is not None and base_url.strip():
        normalized = base_url.strip().rstrip("/")
        new_origin = origin_of(normalized)
        current_origin = origin_of(settings.base_url)
        if new_origin != current_origin:
            if new_origin not in trusted_origins():
                raise ConfigError(
                    "Смена origin отклонена: хоста нет в ZEPHYR_TRUSTED_ORIGINS. Прежний токен не переносится."
                )
            if bearer_token is None:
                settings.bearer_token = ""
            if wiki_bearer_token is None:
                settings.wiki_bearer_token = ""
        settings.base_url = normalized
    if project_key is not None and project_key.strip():
        settings.project_key = project_key.strip()
    if project_id is not None and str(project_id).strip():
        settings.project_id = str(project_id).strip()
    if wiki_url is not None:
        settings.wiki_url = wiki_url.strip().rstrip("/")
    _write_file(settings)
    return settings


def _first_nonempty(*values: str | None) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
