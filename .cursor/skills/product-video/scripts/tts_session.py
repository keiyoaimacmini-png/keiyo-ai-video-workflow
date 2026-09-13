#!/usr/bin/env python3
"""CapCut TTS session: set up Chrome/page/voice/field once, then reuse.

Do not add HOLDs. Lost sessions recover with the existing Chrome MCP HOLD
after MAX_TRANSIENT_RETRIES failed restores.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from constants import HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, MAX_TRANSIENT_RETRIES
from paths import case_root, emit
from workflow_state import atomic_write, hold

SCHEMA = "product_video_tts_session.v1"
SETUP_FLAGS = (
    "chrome_mcp_attached",
    "capcut_tts_page_ready",
    "holiday_twist_selected",
    "tts_input_field_identified",
    "credit_policy_ready",
)


def session_path(project_root, case_id: str):
    return case_root(project_root, case_id) / "tts" / "session.json"


def empty_session(case_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "setup": False,
        "reuse": False,
        "recover_count": 0,
        "field_id": None,
    }


def load_session(project_root, case_id: str) -> dict[str, Any]:
    path = session_path(project_root, case_id)
    if not path.is_file():
        return empty_session(case_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty_session(case_id)
    if data.get("case_id") != case_id:
        return empty_session(case_id)
    return data


def save_session(project_root, data: dict[str, Any]):
    case_id = data["case_id"]
    path = session_path(project_root, case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def missing_setup_flags(observation: dict[str, Any] | None) -> list[str]:
    if not isinstance(observation, dict):
        return list(SETUP_FLAGS)
    return [key for key in SETUP_FLAGS if observation.get(key) is not True]


def session_ready(observation: dict[str, Any] | None) -> bool:
    return not missing_setup_flags(observation)


def prove_session_setup(
    observation: dict[str, Any] | None,
    *,
    recover_count: int = 0,
) -> dict[str, Any]:
    missing = missing_setup_flags(observation)
    if not missing:
        field_id = None
        if isinstance(observation, dict):
            field_id = observation.get("field_id") or observation.get("tts_field_id")
        return {
            "status": "OK",
            "setup": True,
            "reuse": True,
            "recover": False,
            "recover_count": recover_count,
            "field_id": field_id,
            "credit_policy_ready": True,
        }
    if recover_count < MAX_TRANSIENT_RETRIES:
        return {
            "status": "OK",
            "setup": False,
            "reuse": False,
            "recover": True,
            "recover_count": recover_count,
            "missing": missing,
        }
    if isinstance(observation, dict) and observation.get("capcut_login_required") is True:
        return hold(
            "HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED",
            "CapCut login, CAPTCHA, 2FA, or account choice is required",
            generate=False,
            recover=False,
            recover_count=recover_count,
        )
    return hold(
        HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
        "CapCut TTS session could not be restored",
        generate=False,
        recover=False,
        recover_count=recover_count,
        missing=missing,
    )


def may_reuse_session(
    session: dict[str, Any] | None,
    observation: dict[str, Any] | None,
) -> dict[str, Any]:
    stored = session if isinstance(session, dict) else {}
    recover_count = stored.get("recover_count")
    if not isinstance(recover_count, int) or isinstance(recover_count, bool) or recover_count < 0:
        recover_count = 0
    if stored.get("setup") is True and session_ready(observation):
        return {
            "status": "OK",
            "setup": False,
            "reuse": True,
            "recover": False,
            "recover_count": recover_count,
            "skip_mcp_rediscovery": True,
            "skip_chrome_preflight": True,
            "skip_page_research": True,
            "skip_holiday_twist_reselect": True,
            "skip_voice_id_resolve": True,
        }
    return prove_session_setup(observation, recover_count=recover_count)


def record_session_setup(
    project_root,
    case_id: str,
    observation: dict[str, Any],
    *,
    recover_count: int = 0,
) -> dict[str, Any]:
    proved = prove_session_setup(observation, recover_count=recover_count)
    data = load_session(project_root, case_id)
    data["recover_count"] = recover_count
    if proved.get("status") == "OK" and proved.get("setup") is True:
        data["setup"] = True
        data["reuse"] = True
        data["field_id"] = proved.get("field_id")
        save_session(project_root, data)
        proved["session_path"] = session_path(project_root, case_id).as_posix()
        return proved
    data["setup"] = False
    data["reuse"] = False
    save_session(project_root, data)
    return proved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--observation-json")
    parser.add_argument("--prove-setup", action="store_true")
    parser.add_argument("--may-reuse", action="store_true")
    parser.add_argument("--recover-count", type=int, default=0)
    args = parser.parse_args()
    from pathlib import Path

    root = Path(args.project_root)
    observation = json.loads(args.observation_json) if args.observation_json else {}
    if args.may_reuse:
        payload = may_reuse_session(load_session(root, args.case_id), observation)
    elif args.prove_setup:
        payload = record_session_setup(
            root,
            args.case_id,
            observation,
            recover_count=args.recover_count,
        )
    else:
        payload = load_session(root, args.case_id)
        payload["status"] = "OK"
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
