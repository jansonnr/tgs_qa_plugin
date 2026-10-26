"""Метка TMS для кейсов, записанных через apply_plan (create)."""
from __future__ import annotations

import os

ENV_IMPORT_LABEL = "ZEPHYR_IMPORT_LABEL"
DEFAULT_IMPORT_LABEL = "AI_Cursor"


def import_label() -> str:
    value = (os.environ.get(ENV_IMPORT_LABEL) or DEFAULT_IMPORT_LABEL).strip()
    return value or DEFAULT_IMPORT_LABEL


def import_labels_for_zephyr() -> list[str]:
    """Единственная метка при импорте в Zephyr (не из черновика)."""
    return [import_label()]
