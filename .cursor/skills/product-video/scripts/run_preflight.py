#!/usr/bin/env python3
"""Batched production preflight. No writes, TTS generate, or credit spend."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from constants import (
    HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
    HOLD_CHATCUT_UNAVAILABLE,
    HOLD_PREFLIGHT_REQUIRED,
    HUMAN_HOLD_CODES,
    MAX_TRANSIENT_RETRIES,
    TRANSIENT_HOLD_CODES,
)
from paths import emit, helper_path, project_root_from
from prove_material_videos import prove_material_videos
from workflow_state import hold


def load_module(project_root: Path, name: str):
    path = helper_path(project_root, name)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def should_retry(payload: dict[str, Any]) -> bool:
    if payload.get("status") == "OK":
        return False
    code = payload.get("hold")
    if code in HUMAN_HOLD_CODES:
        return False
    return code in TRANSIENT_HOLD_CODES


def retry_call(fn: Callable[[], dict[str, Any]], *, attempts: int = MAX_TRANSIENT_RETRIES) -> dict[str, Any]:
    last: dict[str, Any] = hold(HOLD_PREFLIGHT_REQUIRED, "preflight call did not run")
    for _ in range(max(1, attempts)):
        last = fn()
        if not should_retry(last):
            return last
    return last


def item(name: str, payload: dict[str, Any], *, operator_fix: str | None = None) -> dict[str, Any]:
    row = {
        "name": name,
        "status": payload.get("status"),
        "hold": payload.get("hold"),
        "reason": payload.get("reason"),
    }
    if operator_fix and payload.get("status") != "OK":
        row["operator_fix"] = operator_fix
    return row


def guarded(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        payload = fn()
        if isinstance(payload, dict):
            return payload
        return hold(HOLD_PREFLIGHT_REQUIRED, f"{name} returned non-object")
    except Exception as exc:  # noqa: BLE001
        return hold(HOLD_PREFLIGHT_REQUIRED, f"{name} check crashed: {type(exc).__name__}")


def check_material(project_root: Path, product_model: str) -> dict[str, Any]:
    helper = load_module(project_root, "resolve_product_inputs")
    resolved = helper.resolve_product_inputs(
        project_root,
        product_model,
        material_root_env=os.environ.get("PRODUCT_VIDEO_MATERIAL_ROOT"),
        require_materials=True,
    )
    if resolved.get("status") != "READY":
        return {
            "status": "HOLD",
            "hold": resolved.get("hold") or "HOLD_INPUT_MATERIALS_REQUIRED",
            "reason": resolved.get("reason") or "product inputs are not ready",
        }
    return prove_material_videos(resolved.get("material_root"))


def check_gemini(*, probe_fn: Callable[[], dict[str, Any]], print_fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    probed = retry_call(probe_fn)
    if probed.get("status") != "OK":
        return probed
    printed = retry_call(print_fn)
    if printed.get("status") != "OK":
        return printed
    text = printed.get("last_text") or printed.get("draft") or ""
    if not str(text).strip():
        return hold("HOLD_GEMINI_CLI_NOT_VERIFIED", "text-only one-shot returned empty body")
    return {
        "status": "OK",
        "hold": None,
        "model_required": probed.get("model_required") or "gemini-3.8-flash",
        "draft_chars": len(str(text)),
    }


def chrome_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "Google Chrome.app/Contents/MacOS/Google Chrome"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def chrome_devtools_path() -> Path:
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "DevToolsActivePort"


def read_devtools_active_port(path: Path | None = None) -> dict[str, Any]:
    dest = path or chrome_devtools_path()
    if not dest.is_file():
        return hold(HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "Chrome DevToolsActivePort is missing")
    lines = dest.read_text(encoding="utf-8").splitlines()
    if not lines:
        return hold(HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "Chrome DevToolsActivePort is empty")
    port = lines[0].strip()
    ws_path = lines[1].strip() if len(lines) > 1 else ""
    if not port.isdigit():
        return hold(HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "Chrome debug port is not a number")
    if "/devtools/browser/" not in ws_path:
        return hold(
            HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
            "Chrome websocket path has no browser id; enable remote debugging",
        )
    return {"status": "OK", "port": int(port), "ws_path": ws_path}


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def cdp_http_ok(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urlopen(url, timeout=2) as response:
            return int(getattr(response, "status", 0) or 0) == 200
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def check_chrome_local(*, running_fn=chrome_running, port_file_fn=read_devtools_active_port) -> dict[str, Any]:
    if not running_fn():
        return hold(HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "Google Chrome.app is not running")
    info = port_file_fn()
    if info.get("status") != "OK":
        return info
    port = int(info["port"])
    if not port_listening(port):
        return hold(HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "Chrome debug port is not listening")
    if not cdp_http_ok(port):
        return hold(
            HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
            "Chrome debug HTTP is not usable; enable chrome://inspect/#remote-debugging",
        )
    return {"status": "OK", "hold": None, "port": port}


def check_drive(project_root: Path, product_model: str, *, live: bool) -> dict[str, Any]:
    helper = load_module(project_root, "upload_drive_local_file")
    client = helper.load_oauth_client(project_root)
    refresh = helper.load_refresh_token(project_root)
    if client is None or refresh is None:
        return hold(
            helper.HOLD_BYTES,
            "missing runtime Drive OAuth; place .runtime/drive-oauth-client.json and run --login at repo root",
        )
    if not live:
        return {"status": "OK", "hold": None, "oauth_present": True, "folder_checked": False}
    token = helper.resolve_access_token(project_root, env=dict(os.environ), http=helper.default_http)
    if isinstance(token, dict):
        return token
    try:
        parent = helper.locate_parent(token, product_model, helper.default_http)
    except helper.DriveHttpError:
        return hold(
            "HOLD_DRIVE_LOOKUP_TRANSIENT",
            "Drive folder lookup failed; retry later or rerun --login",
        )
    if isinstance(parent, dict):
        return parent
    return {"status": "OK", "hold": None, "parent_title": product_model}


def observation_check(obs: dict[str, Any], key: str, code: str, reason: str) -> dict[str, Any]:
    if key not in obs:
        return hold(code, reason)
    if obs.get(key) is True:
        return {"status": "OK", "hold": None}
    return hold(code, reason)


def merge_preflight(items: list[dict[str, Any]]) -> dict[str, Any]:
    fixes = []
    seen = set()
    failed = []
    for row in items:
        if row.get("status") == "OK":
            continue
        failed.append(row)
        fix = row.get("operator_fix")
        if fix and fix not in seen:
            seen.add(fix)
            fixes.append(fix)
    if not failed:
        return {"status": "READY", "hold": None, "operator_fixes": [], "items": items}
    return {
        "status": "HOLD",
        "hold": HOLD_PREFLIGHT_REQUIRED,
        "reason": "start-time preflight found operator fixes",
        "operator_fixes": fixes,
        "items": items,
        "message_ja": "開始前に直すこと:\n" + "\n".join(f"- {line}" for line in fixes),
    }


def run_preflight(
    project_root: Path,
    *,
    product_model: str,
    observation: dict[str, Any] | None = None,
    live: bool = False,
    gemini_probe_fn: Callable[[], dict[str, Any]] | None = None,
    gemini_print_fn: Callable[[], dict[str, Any]] | None = None,
    chrome_fn: Callable[[], dict[str, Any]] | None = None,
    drive_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = project_root_from(project_root)
    obs = observation or {}
    items: list[dict[str, Any]] = []

    material = guarded("material", lambda: check_material(root, product_model))
    items.append(
        item(
            "material",
            material,
            operator_fix="素材フォルダに非0 byteの動画を戻す（元素材は移動・削除しない）",
        )
    )

    def run_gemini() -> dict[str, Any]:
        probe = gemini_probe_fn
        printer = gemini_print_fn
        if probe is None or printer is None:
            gemini = load_module(root, "send_gemini_cli_prompt")

            def probe() -> dict[str, Any]:
                return gemini.probe()

            def printer() -> dict[str, Any]:
                if not live:
                    return {"status": "OK", "last_text": "PONG"}
                return gemini.probe_print()

        return check_gemini(probe_fn=probe, print_fn=printer)

    gemini_result = guarded("gemini", run_gemini)
    gemini_fix = "Terminal で `agy` を起動して Google ログインする"
    if gemini_result.get("hold") == "HOLD_GEMINI_CLI_NOT_VERIFIED":
        gemini_fix = "Antigravity CLI の一発印刷を修復する（上振れ課金は使わない）"
    items.append(item("gemini", gemini_result, operator_fix=gemini_fix))

    chrome_local = retry_call(
        lambda: guarded("chrome_local", chrome_fn or check_chrome_local)
    )
    items.append(
        item(
            "chrome_local",
            chrome_local,
            operator_fix="Google Chrome.app を起動し、chrome://inspect/#remote-debugging で remote debugging を許可する",
        )
    )
    chrome_mcp = observation_check(
        obs,
        "chrome_mcp_attached",
        HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
        "Playwright MCP --cdp-endpoint=chrome could not attach",
    )
    items.append(
        item(
            "chrome_mcp",
            chrome_mcp,
            operator_fix="Google Chrome.app を起動し、chrome://inspect/#remote-debugging で remote debugging を許可する",
        )
    )
    if chrome_mcp.get("status") == "OK":
        capcut_tts = observation_check(
            obs,
            "capcut_tts_reachable",
            HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
            "CapCut official Text to Speech is not reachable",
        )
        items.append(
            item(
                "capcut_tts",
                capcut_tts,
                operator_fix="起動済み Chrome で CapCut 公式 Text to Speech を開ける状態にする",
            )
        )
        capcut_login = observation_check(
            obs,
            "capcut_logged_in",
            "HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED",
            "CapCut login, CAPTCHA, 2FA, or account choice is required",
        )
        items.append(
            item(
                "capcut_login",
                capcut_login,
                operator_fix="CapCut のログイン / CAPTCHA / 2FA / アカウント選択を完了する",
            )
        )
        holiday = observation_check(
            obs,
            "holiday_twist_available",
            HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
            "Holiday Twist is not available",
        )
        items.append(
            item(
                "holiday_twist",
                holiday,
                operator_fix="CapCut 公式 Text to Speech でホリデーツイストが選べる状態にする",
            )
        )

    chatcut = observation_check(
        obs,
        "chatcut_connected",
        HOLD_CHATCUT_UNAVAILABLE,
        "ChatCut editor tools are not available",
    )
    items.append(
        item(
            "chatcut",
            chatcut,
            operator_fix="ChatCut MCP を再接続し、project 作成と inspect/edit が使えることを確認する",
        )
    )

    drive = retry_call(
        lambda: guarded(
            "drive",
            drive_fn or (lambda: check_drive(root, product_model, live=live)),
        )
    )
    items.append(
        item(
            "drive",
            drive,
            operator_fix="リポジトリルートで Drive OAuth を置き、upload_drive_local_file.py --login する",
        )
    )

    merged = merge_preflight(items)
    merged["product_model"] = product_model
    merged["live"] = live
    merged["writes"] = False
    merged["tts_generated"] = False
    merged["credits_consumed"] = False
    return merged


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    first = {"status": "HOLD", "hold": HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE}
    ok = {"status": "OK"}
    calls = {"n": 0}

    def flaky() -> dict[str, Any]:
        calls["n"] += 1
        return ok if calls["n"] >= 2 else first

    recovered = retry_call(flaky, attempts=3)
    check("retry-recovers-without-operator", recovered.get("status") == "OK" and calls["n"] == 2)

    login = retry_call(lambda: {"status": "HOLD", "hold": "HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED"}, attempts=3)
    check("retry-does-not-loop-login", login.get("hold") == "HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED")

    batch_calls = {"n": 0}

    def batched() -> dict[str, Any]:
        batch_calls["n"] += 1
        return {"status": "HOLD", "hold": HOLD_PREFLIGHT_REQUIRED}

    retry_call(batched, attempts=3)
    check("retry-does-not-loop-batched-hold", batch_calls["n"] == 1)

    still = retry_call(lambda: first, attempts=3)
    check("retry-stops-at-max", still.get("hold") == HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE)

    merged = merge_preflight(
        [
            item("chrome_local", hold(HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "x"), operator_fix="Chrome remote debugging OFF"),
            item("drive", hold("HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE", "x"), operator_fix="Drive OAuth期限切れ"),
            item("material", {"status": "OK"}),
        ]
    )
    check("batch-hold-code", merged.get("hold") == HOLD_PREFLIGHT_REQUIRED)
    check("batch-two-fixes", merged.get("operator_fixes") == ["Chrome remote debugging OFF", "Drive OAuth期限切れ"])
    check("batch-does-not-stop-at-first", len(merged.get("operator_fixes") or []) == 2)
    check("batch-message", "開始前に直すこと" in (merged.get("message_ja") or ""))
    ready = merge_preflight([item("material", {"status": "OK"}), item("gemini", {"status": "OK"})])
    check("ready-when-all-ok", ready.get("status") == "READY")
    try:
        helper = load_module(Path(__file__).resolve().parents[4], "upload_drive_local_file")
        check("load-drive-helper", hasattr(helper, "load_oauth_client"))
    except Exception as exc:  # noqa: BLE001
        check("load-drive-helper", False)
        print(f"FAIL load-drive-helper {type(exc).__name__}: {exc}", flush=True)
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: run_preflight", flush=True)
        return 1
    print("SELF-TEST PASSED: run_preflight")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--product-model")
    parser.add_argument("--observation-json", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.project_root is None or not args.product_model:
        parser.error("--project-root and --product-model are required unless --self-test is used")
    observation = {}
    if args.observation_json:
        observation = json.loads(args.observation_json.read_text(encoding="utf-8"))
    payload = run_preflight(
        args.project_root,
        product_model=args.product_model,
        observation=observation,
        live=args.live,
    )
    emit(payload)
    return 0 if payload.get("status") == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
