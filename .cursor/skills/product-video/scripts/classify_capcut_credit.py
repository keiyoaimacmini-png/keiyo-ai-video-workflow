#!/usr/bin/env python3
"""Classify a CapCut Holiday Twist credit dialog. Existing-balance consume vs new contract."""

from __future__ import annotations

import argparse
import json
from typing import Any

from constants import HOLD_CAPCUT_CREDIT_UNVERIFIED, HOLD_CAPCUT_NEW_PURCHASE_REQUIRED
from workflow_state import hold

EXISTING_TITLE = "Credits will be consumed"
GOT_IT = "Got it"
CANCEL = "Cancel"

NEW_CONTRACT_FLAGS = (
    ("pro_subscription", "Pro monthly or annual contract"),
    ("free_trial", "free trial signup"),
    ("purchase_credits", "additional credit purchase"),
    ("auto_reload", "auto reload"),
    ("new_payment", "new payment"),
    ("plan_change", "plan or contract change"),
    ("monthly_or_annual_price", "monthly or annual price"),
    ("payment_form", "payment form"),
)


def _has_button(buttons: object, label: str) -> bool:
    if not isinstance(buttons, list):
        return False
    return any(isinstance(item, str) and item.strip() == label for item in buttons)


def classify_capcut_credit(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        return hold(
            HOLD_CAPCUT_CREDIT_UNVERIFIED,
            "credit dialog record must be an object",
            approve_got_it=False,
        )
    for key, label in NEW_CONTRACT_FLAGS:
        if record.get(key) is True:
            return hold(
                HOLD_CAPCUT_NEW_PURCHASE_REQUIRED,
                f"do not auto-approve {label}",
                approve_got_it=False,
                blocked_signal=key,
            )
    title = record.get("title")
    credits = record.get("credits_required")
    buttons = record.get("buttons")
    credits_ok = isinstance(credits, (int, float)) and not isinstance(credits, bool) and credits > 0
    existing = (
        title == EXISTING_TITLE
        and credits_ok
        and _has_button(buttons, CANCEL)
        and _has_button(buttons, GOT_IT)
        and all(record.get(key) is False for key, _label in NEW_CONTRACT_FLAGS)
    )
    if existing:
        return {
            "status": "OK",
            "hold": None,
            "approve_got_it": True,
            "existing_balance_consumption": True,
            "body_contains_pro_ignored": bool(record.get("body_contains_pro")),
        }
    return hold(
        HOLD_CAPCUT_CREDIT_UNVERIFIED,
        "cannot distinguish existing-balance consumption from a new contract or purchase",
        approve_got_it=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-json", required=True)
    args = parser.parse_args()
    payload = classify_capcut_credit(json.loads(args.record_json))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("approve_got_it") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
