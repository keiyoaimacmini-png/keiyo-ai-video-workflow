#!/usr/bin/env python3
"""Advance a completed stage only after its receipt is saved."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paths import emit
from workflow_state import complete_stage, hold, load_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--receipt-json", required=True)
    parser.add_argument("--next-stage")
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt_json)
        state = load_state(args.project_root, args.case_id)
        payload = complete_stage(
            args.project_root,
            state,
            args.stage,
            receipt,
            next_stage=args.next_stage,
        )
        emit(payload)
        return 0
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        emit(hold("HOLD_STAGE_ADVANCE_FAILED", str(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
