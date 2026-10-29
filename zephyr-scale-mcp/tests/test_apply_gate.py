from __future__ import annotations

import time

from zephyr_scale_mcp.apply_gate import ApplyTokenStore


def test_token_single_use_and_plan_hash_binding() -> None:
    store = ApplyTokenStore()
    token, _ = store.issue(plan_hash="abc123", ttl_seconds=120)
    assert store.consume(token, plan_hash="abc123") is not None
    assert store.consume(token, plan_hash="abc123") is None


def test_token_rejects_wrong_plan_hash() -> None:
    store = ApplyTokenStore()
    token, _ = store.issue(plan_hash="plan-a", ttl_seconds=120)
    assert store.consume(token, plan_hash="plan-b") is None


def test_resume_requires_consumed_token() -> None:
    store = ApplyTokenStore()
    token, _ = store.issue(plan_hash="plan-a", ttl_seconds=120)
    assert store.authorize_resume(token, plan_hash="plan-a") is False
    assert store.consume(token, plan_hash="plan-a") is not None
    assert store.authorize_resume(token, plan_hash="plan-a") is True
    assert store.authorize_resume(token, plan_hash="plan-b") is False


def test_token_expires() -> None:
    store = ApplyTokenStore()
    token, expires_at = store.issue(plan_hash="x", ttl_seconds=60)
    record = store._tokens[token]  # noqa: SLF001 — тест
    store._tokens[token] = type(record)(
        plan_hash=record.plan_hash,
        run_id=record.run_id,
        expires_at=time.time() - 1,
        used=False,
    )
    assert store.consume(token, plan_hash="x") is None
    assert expires_at > time.time()
