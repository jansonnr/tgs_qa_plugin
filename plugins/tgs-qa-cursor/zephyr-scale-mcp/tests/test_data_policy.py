from __future__ import annotations

from pathlib import Path

import pytest

from zephyr_scale_mcp.data_policy import (
    QaPathError,
    redact_operations,
    resolve_attachment_path,
    resolve_qa_log_dir,
    scan_plan,
    to_agent,
)
from zephyr_scale_mcp.plan_rules import PlanRejected, validate_plan


def _plan(name: str = "Обычный кейс") -> dict:
    return {
        "search_status": "ok",
        "draft_revision": 1,
        "operations": [{"case_id": "c1", "action": "create", "name": name}],
    }


def test_secret_in_plan_blocks_apply_until_decision() -> None:
    plan = _plan("token=supersecretvalue")
    with pytest.raises(PlanRejected) as caught:
        validate_plan(plan)
    assert caught.value.code == "SECRETS_UNRESOLVED"
    finding_id = scan_plan(plan)[0]["id"]
    plan["secret_decisions"] = {finding_id: "exclude"}
    validate_plan(plan)
    redacted = redact_operations(plan)
    assert redacted[0]["name"] == "[secret]"


def test_confirmed_secret_stays_in_the_operation() -> None:
    plan = _plan("token=supersecretvalue")
    with pytest.raises(PlanRejected) as caught:
        validate_plan(plan)
    finding_id = scan_plan(plan)[0]["id"]
    plan["secret_decisions"] = {finding_id: "confirm"}
    validate_plan(plan)
    assert redact_operations(plan)[0]["name"] == "token=supersecretvalue"


def test_attachment_path_must_live_under_qa(tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(QaPathError):
        resolve_attachment_path(str(outside))
    allowed = tmp_path / ".qa" / "attachments" / "shot.png"
    allowed.parent.mkdir(parents=True)
    allowed.write_bytes(b"png")
    assert resolve_attachment_path(str(allowed)) == allowed.resolve()


def test_qa_log_dir_rejects_paths_outside_qa(tmp_path: Path) -> None:
    allowed = tmp_path / ".qa"
    assert resolve_qa_log_dir(str(allowed)).name == "apply-logs"
    with pytest.raises(Exception):
        resolve_qa_log_dir(str(tmp_path / "notes"))
    with pytest.raises(Exception):
        resolve_qa_log_dir(str(allowed / ".." / "notes"))


def test_agent_error_drops_raw_body_and_masks_secret() -> None:
    public = to_agent(
        {
            "ok": False,
            "status_code": 400,
            "url": "https://track.example/rest?token=supersecretvalue",
            "data": {"message": "token=supersecretvalue"},
        }
    )
    assert "url" not in public
    assert "data" not in public
    assert "supersecretvalue" not in public["error"]


def test_agent_success_reports_truncated_volume() -> None:
    public = to_agent({"ok": True, "content_markdown": "а" * 5000})
    assert public["context"]["original_chars"] == 5000
    assert public["context"]["returned_chars"] == 4000
    assert public["context"]["truncated"] == 1
    assert len(public["content_markdown"]) == 4000
