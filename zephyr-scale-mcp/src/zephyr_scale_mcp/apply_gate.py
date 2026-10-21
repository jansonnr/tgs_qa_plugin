from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass

WRITE_GATE_DENIED = "WRITE_GATE_DENIED"
WRITE_GATE_MESSAGE = (
    "Запись в Zephyr запрещена без apply_token. "
    "Сначала prepare_apply (после подтверждения пользователем), затем apply_plan."
)


def direct_write_allowed() -> bool:
    return os.environ.get("ZEPHYR_ALLOW_DIRECT_WRITE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def write_gate_denied_payload() -> dict[str, object]:
    return {"ok": False, "error": WRITE_GATE_MESSAGE, "code": WRITE_GATE_DENIED}


@dataclass(frozen=True)
class ApplyTokenRecord:
    plan_hash: str
    run_id: str | None
    expires_at: float
    used: bool = False


class ApplyTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, ApplyTokenRecord] = {}

    def issue(
        self,
        *,
        plan_hash: str,
        run_id: str | None = None,
        ttl_seconds: int = 900,
    ) -> tuple[str, float]:
        normalized = plan_hash.strip()
        if not normalized:
            raise ValueError("plan_hash обязателен.")
        if ttl_seconds < 60:
            raise ValueError("ttl_seconds не меньше 60.")
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + ttl_seconds
        self._tokens[token] = ApplyTokenRecord(
            plan_hash=normalized,
            run_id=run_id.strip() if run_id else None,
            expires_at=expires_at,
        )
        return token, expires_at

    def consume(self, apply_token: str, *, plan_hash: str) -> ApplyTokenRecord | None:
        key = apply_token.strip()
        record = self._tokens.get(key)
        if record is None:
            return None
        if record.used:
            return None
        if time.time() > record.expires_at:
            return None
        if record.plan_hash != plan_hash.strip():
            return None
        self._tokens[key] = ApplyTokenRecord(
            plan_hash=record.plan_hash,
            run_id=record.run_id,
            expires_at=record.expires_at,
            used=True,
        )
        return record


_apply_token_store = ApplyTokenStore()


def get_apply_token_store() -> ApplyTokenStore:
    return _apply_token_store
