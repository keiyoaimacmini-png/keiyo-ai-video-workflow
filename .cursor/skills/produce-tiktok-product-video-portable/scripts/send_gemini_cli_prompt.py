#!/usr/bin/env python3
"""Send one rendered prompt through Antigravity CLI (agy) on this Mac.

One-shot print only. Empty workspace. No Gemini API key. Do not launch
Gemini.app, Chrome.app, or the agent-controlled browser. If this path fails,
HOLD. Do not paste the prompt for the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


HOLD_CLI = "HOLD_GEMINI_CLI_NOT_VERIFIED"
HOLD_LOGIN = "HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED"
HOLD_MODEL = "HOLD_GEMINI_MODEL_NOT_VERIFIED"
AGY_NAME = "agy"
MODEL_REQUIRED = "gemini-3.8-flash"
MODEL_LABEL = "Gemini 3.8 Flash"
EFFORT_REQUIRED = "medium"
PRINT_TIMEOUT = "2m"
TRANSPORT_PREFIX = (
    "これはテキスト生成だけのタスクです。\n"
    "RunCommand、ReadFile、WriteFile、Web、MCPその他のツールを一切使用しないでください。\n"
    "workspaceを調査しないでください。\n"
    "コマンドを実行しないでください。\n"
    "以下に与えた情報だけを使って、完成した回答本文を直接出力してください。\n"
    "ツール利用の提案・確認・前置きも不要です。\n"
)
API_ENV_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTIGRAVITY_API_KEY",
    "GOOGLE_GENAI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
LOGIN_MARKERS = (
    "you are not logged into antigravity",
    "authentication required",
    "eligibility check failed",
    "couldn't verify account",
    "verify your account",
)
QUOTA_MARKERS = (
    "quota reached",
    "quota exceeded",
    "rate limit",
    "resource exhausted",
)
CREDIT_MARKERS = (
    "purchase ai credits",
    "buy additional",
    "useg1credits",
)


def hold(code: str, reason: str) -> dict[str, str]:
    return {"status": "HOLD", "hold": code, "reason": reason}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scrub_env(source: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(source if source is not None else os.environ)
    for key in API_ENV_KEYS:
        env.pop(key, None)
    return env


def combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout or ''}\n{result.stderr or ''}"


def classify_failure(text: str) -> dict[str, str]:
    compact = text.lower()
    if any(marker in compact for marker in LOGIN_MARKERS):
        return hold(
            HOLD_LOGIN,
            "Antigravity CLI is not logged in with the Google AI subscription account. "
            "In Terminal run `agy`, complete Google login, set AI Credit Overages to Never, then retry this helper. "
            "Do not paste passwords or API keys",
        )
    if any(marker in compact for marker in CREDIT_MARKERS):
        return hold(
            HOLD_CLI,
            "Antigravity asked to use or buy AI credits. Do not enable overages. Wait for the included quota",
        )
    if any(marker in compact for marker in QUOTA_MARKERS):
        return hold(
            HOLD_CLI,
            "Antigravity included quota is exhausted. Do not buy credits or enable overages. Wait for refresh",
        )
    return hold(HOLD_CLI, "Antigravity CLI did not return a one-shot Gemini 3.8 Flash draft")


def extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    last: dict[str, Any] | None = None
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            data, _end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            last = data
    return last


def apply_transport_prefix(prompt: str) -> str:
    """Prepend a transport-only no-tools prefix. Do not rewrite the rendered body."""
    if prompt.startswith(TRANSPORT_PREFIX):
        return prompt
    return TRANSPORT_PREFIX + prompt


def extract_draft(payload: dict[str, Any] | None) -> str:
    """Return model draft text only. A SUCCESS envelope with empty response is not a draft."""
    if not payload:
        return ""
    for key in ("response", "text", "output"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def response_text(payload: dict[str, Any] | None, stdout: str) -> str:
    draft = extract_draft(payload)
    if draft:
        return draft
    return ""


def model_matches(payload: dict[str, Any] | None, blob: str, requested: str | None = None) -> bool:
    blob_l = blob.lower()
    other_models = ("gemini-3.7", "gemini-3.6", "gemini-3.1-pro", "claude", "gpt-oss")
    if any(token in blob_l for token in other_models) and MODEL_REQUIRED not in blob_l:
        return False
    if MODEL_REQUIRED in blob_l or MODEL_LABEL.lower() in blob_l:
        return True
    if not payload:
        return False
    for key in ("model", "model_id", "modelId"):
        value = payload.get(key)
        if isinstance(value, str) and MODEL_REQUIRED in value.lower():
            return True
    usage = payload.get("usage")
    if isinstance(usage, dict):
        model = usage.get("model")
        if isinstance(model, str) and MODEL_REQUIRED in model.lower():
            return True
    status = payload.get("status")
    if isinstance(status, str) and status.upper() == "SUCCESS" and requested == MODEL_REQUIRED:
        return True
    return False


def find_agy() -> str | None:
    return shutil.which(AGY_NAME)


def run_agy(args: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=scrub_env(),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def probe() -> dict[str, Any]:
    agy = find_agy()
    if not agy:
        return hold(HOLD_CLI, "agy is not on PATH; install Antigravity CLI and retry this helper")
    with tempfile.TemporaryDirectory(prefix="gemini-cli-probe-") as tmp:
        tmp_path = Path(tmp)
        log_file = tmp_path / "agy.log"
        try:
            result = run_agy(
                [agy, "--log-file", str(log_file), "models"],
                cwd=tmp_path,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return hold(HOLD_CLI, "agy models timed out")
        except OSError as exc:
            return hold(HOLD_CLI, str(exc))
    blob = combined_output(result)
    if result.returncode != 0:
        classified = classify_failure(blob)
        if classified.get("hold") == HOLD_LOGIN:
            return classified
        return hold(HOLD_CLI, "agy models failed; install or repair Antigravity CLI")
    login_fail = classify_failure(blob)
    if login_fail.get("hold") == HOLD_LOGIN:
        return login_fail
    return {
        "status": "OK",
        "action": "probe",
        "cli": AGY_NAME,
        "model_required": MODEL_REQUIRED,
        "api_key_used": False,
        "note": "Logged-in Antigravity CLI is required. Do not set GEMINI_API_KEY. Do not enable AI Credit overages.",
    }


def agy_print_command(agy: str, prompt: str, log_file: Path) -> list[str]:
    return [
        agy,
        "--print",
        prompt,
        "--output-format",
        "json",
        "--model",
        MODEL_REQUIRED,
        "--effort",
        EFFORT_REQUIRED,
        "--sandbox",
        "--disable-slash-commands",
        "--print-timeout",
        PRINT_TIMEOUT,
        "--log-file",
        str(log_file),
    ]


def send_prompt(prompt: str) -> dict[str, Any]:
    if not prompt.strip():
        return hold(HOLD_CLI, "prompt file is empty")
    agy = find_agy()
    if not agy:
        return hold(HOLD_CLI, "agy is not on PATH; install Antigravity CLI and retry this helper")
    to_send = apply_transport_prefix(prompt)
    with tempfile.TemporaryDirectory(prefix="gemini-cli-script-") as tmp:
        tmp_path = Path(tmp)
        log_file = tmp_path / "agy.log"
        cmd = agy_print_command(agy, to_send, log_file)
        try:
            result = run_agy(cmd, cwd=tmp_path, timeout=150)
        except subprocess.TimeoutExpired:
            return hold(HOLD_CLI, "agy print timed out")
        except OSError as exc:
            return hold(HOLD_CLI, str(exc))
        leftover = [
            path.name
            for path in tmp_path.iterdir()
            if path.is_file() and path.name != "agy.log" and path.suffix.lower() in {".py", ".md", ".json", ".txt"}
        ]
    blob = combined_output(result)
    if leftover:
        return hold(HOLD_CLI, "agy wrote workspace files; rerun as a one-shot with no file edits")
    parsed = extract_json_object(result.stdout or "")
    text = extract_draft(parsed)
    if result.returncode != 0 or not text:
        return classify_failure(blob)
    if not model_matches(parsed, blob, requested=MODEL_REQUIRED):
        return hold(
            HOLD_MODEL,
            f"Antigravity CLI model is not {MODEL_LABEL} ({MODEL_REQUIRED}). Do not fall back to Auto, Pro, or another Flash",
        )
    return {
        "status": "OK",
        "action": "send",
        "cli": AGY_NAME,
        "model_required": MODEL_REQUIRED,
        "model_label": MODEL_LABEL,
        "api_key_used": False,
        "overages": "never",
        "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt),
        "last_text": text,
        "note": "Draft came from Antigravity CLI one-shot print on the Google account subscription quota. Do not store cookies, tokens, or API keys.",
    }


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    source = Path(__file__).read_text(encoding="utf-8")
    cmd = agy_print_command("agy", "hello", Path("/tmp/agy.log"))
    check("print-one-shot", cmd[1] == "--print")
    check("pins-model", MODEL_REQUIRED in cmd and MODEL_REQUIRED == "gemini-3.8-flash")
    check("pins-effort", cmd[cmd.index("--effort") + 1] == EFFORT_REQUIRED if "--effort" in cmd else False)
    check("sandbox", "--sandbox" in cmd)
    check("no-skip-permissions", all(not flag.startswith("--dangerously") for flag in cmd))
    command_src = Path(__file__).read_text(encoding="utf-8").split("def self_test")[0]
    check("no-dangerously-in-command", "--dangerously-skip-permissions" not in command_src)
    check("transport-prefix", "これはテキスト生成だけのタスクです" in TRANSPORT_PREFIX and "これはテキスト生成だけのタスクです" in source)
    check("bans-runcommand", "RunCommand" in TRANSPORT_PREFIX and "使用しない" in TRANSPORT_PREFIX)
    check("bans-file-rw", "ReadFile" in TRANSPORT_PREFIX and "WriteFile" in TRANSPORT_PREFIX)
    check("bans-web-mcp", "Web" in TRANSPORT_PREFIX and "MCP" in TRANSPORT_PREFIX)
    body = "あなたはTikTok向けの商品紹介ショート動画の台本作家です。\n"
    prefixed = apply_transport_prefix(body)
    check("prefix-preserves-body", prefixed.startswith(TRANSPORT_PREFIX) and prefixed.endswith(body) and prefixed[len(TRANSPORT_PREFIX):] == body)
    check("prefix-idempotent", apply_transport_prefix(prefixed) == prefixed)
    empty_success = extract_json_object('{"status":"SUCCESS","response":""}')
    check("empty-success-not-ok", extract_draft(empty_success) == "")
    check(
        "empty-success-stdout-not-draft",
        response_text(empty_success, '{"status":"SUCCESS","response":""}') == "",
    )
    check("mentions-no-app", "Do not launch" in source and "Gemini.app" in source)
    env = scrub_env({"GEMINI_API_KEY": "secret", "PATH": "/usr/bin", "HOME": "/tmp"})
    check("scrub-api-key", "GEMINI_API_KEY" not in env)
    check("keep-path", env.get("PATH") == "/usr/bin")
    login = classify_failure("You are not logged into Antigravity.")
    check("login-hold", login.get("hold") == HOLD_LOGIN)
    quota = classify_failure("Individual quota reached")
    check("quota-hold", quota.get("hold") == HOLD_CLI)
    parsed = extract_json_object('noise\n{"response":"昼の車内って熱いよね？","model":"gemini-3.8-flash"}\n')
    check("parse-json", isinstance(parsed, dict) and parsed.get("response", "").startswith("昼"))
    check("model-match", model_matches(parsed, "gemini-3.8-flash"))
    check("model-reject", model_matches({"model": "gemini-3-flash"}, "auto") is False)
    check(
        "success-omits-model",
        model_matches({"status": "SUCCESS", "response": "ok"}, "{}", requested=MODEL_REQUIRED),
    )
    check(
        "success-other-model",
        model_matches({"status": "SUCCESS"}, "claude-sonnet-4-6", requested=MODEL_REQUIRED) is False,
    )
    check("hold-cli", hold(HOLD_CLI, "x")["hold"] == HOLD_CLI)
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: send_gemini_cli_prompt", flush=True)
        return 1
    print("SELF-TEST PASSED: send_gemini_cli_prompt")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    try:
        if args.probe:
            payload = probe()
            emit(payload)
            return 0 if payload.get("status") == "OK" else 2
        if args.prompt_file is None:
            parser.error("--prompt-file is required unless --probe or --self-test is used")
        prompt = args.prompt_file.read_text(encoding="utf-8")
        payload = send_prompt(prompt)
        emit(payload)
        return 0 if payload.get("status") == "OK" else 2
    except (OSError, TimeoutError, RuntimeError, UnicodeError) as exc:
        emit(hold(HOLD_CLI, str(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
