#!/usr/bin/env python3
"""Bind only explicit 案Nで台本OK. Never infer approval."""

from __future__ import annotations

import re
from typing import Any

from constants import SCRIPT_APPROVAL_RE
from workflow_state import hold

PATTERN = re.compile(SCRIPT_APPROVAL_RE)


def bind_script_selection(utterance: str, state: dict[str, Any]) -> dict[str, Any]:
    text = (utterance or "").strip()
    match = PATTERN.fullmatch(text)
    if not match:
        return hold(
            "HOLD_SCRIPT_SELECTION_REQUIRED",
            "approval must be exactly 案Nで台本OK",
            utterance_accepted=False,
        )
    variant_id = int(match.group(1))
    available = state.get("script_variant_ids") or []
    if available and variant_id not in available:
        return hold("HOLD_SCRIPT_VARIANT_MISSING", f"案{variant_id} is not in the presented set")
    return {"status": "OK", "variant_id": variant_id, "approval": text}


def is_delivery_approval(utterance: str) -> bool:
    from constants import DELIVERY_APPROVAL

    return (utterance or "").strip() == DELIVERY_APPROVAL
