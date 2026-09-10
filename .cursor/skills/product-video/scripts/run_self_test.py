#!/usr/bin/env python3
"""Local tests for /product-video. No live production, Gemini, CapCut, or Drive."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPTS))

from assembly import assemble_plan, select_cut  # noqa: E402
from bind_script_selection import bind_script_selection  # noqa: E402
from constants import (  # noqa: E402
    DELIVERY_APPROVAL,
    NARRATION_SPEED,
    OLD_SKILL_MARKERS,
    OPERATOR_ROUGH_MESSAGE,
)
from delivery import may_complete, may_purge, may_start_job  # noqa: E402
from dispatch import dispatch  # noqa: E402
from narration import gate_tts_generate, narration_speed, prepare_tts_input, record_clip, write_manifest  # noqa: E402
from parse_gemini_scripts import parse_gemini_scripts  # noqa: E402
from paths import git_tracks, helper_path, helper_relpath, missing_git_tracked_helpers  # noqa: E402
from prepare import build_product_inputs, create_new_case, finish_prepare  # noqa: E402
from prepare_tts_field import compare_tts_readback, diagnose_mismatch, is_pre_write_empty  # noqa: E402
from render_script_prompt import load_template, render_script_prompt  # noqa: E402
from rough_edit import build_rough_edit  # noqa: E402
from script_fidelity import assert_immutable  # noqa: E402
from script_stage import accept_gemini_output  # noqa: E402
from workflow_state import (  # noqa: E402
    complete_stage,
    empty_state,
    load_state,
    save_state,
    validate_compact,
)


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"PASS {name}")
        return
    FAILURES.append(name if not detail else f"{name}: {detail}")
    print(f"FAIL {name}" + (f" ({detail})" if detail else ""))


def sample_variant(n: int, title: str) -> str:
    return (
        f"【案{n}：{title}】\n"
        "想定完成尺：約45秒\n"
        "※ナレーション1.2倍速での想定\n"
        "カット1\n"
        "シチュエーション：\n"
        f"「車内でハンドルを握る人物」\n"
        "セリフ：\n"
        f"「車、サウナすぎん？{n}」\n"
        "カット2\n"
        "シチュエーション：\n"
        "「サンシェードを広げる手元」\n"
        "セリフ：\n"
        "「これ一枚で全然違う。」\n"
    )


def sample_scripts(count: int) -> str:
    titles = ["熱中症型", "時短型", "共感型", "使用シーン型", "比較型", "余分類"]
    body = "".join(sample_variant(i, titles[i - 1]) for i in range(1, count + 1))
    return body + "案1は熱さ、案2は時短、案3は共感。\n"


def fake_project(tmp: Path) -> Path:
    skill = tmp / ".cursor" / "skills" / "product-video"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# product-video\n", encoding="utf-8")
    refs = skill / "references"
    refs.mkdir()
    shutil.copy(
        REPO / ".cursor" / "skills" / "product-video" / "references" / "gemini-script-instructions.md",
        refs / "gemini-script-instructions.md",
    )
    owned_scripts = skill / "scripts"
    owned_scripts.mkdir()
    shutil.copy(
        REPO / ".cursor" / "skills" / "product-video" / "scripts" / "prove_tts_textarea.py",
        owned_scripts / "prove_tts_textarea.py",
    )
    shutil.copy(
        REPO / ".cursor" / "skills" / "product-video" / "scripts" / "prepare_tts_field.py",
        owned_scripts / "prepare_tts_field.py",
    )
    helper_dir = tmp / ".cursor" / "skills" / "produce-tiktok-product-video-portable" / "scripts"
    helper_dir.mkdir(parents=True)
    for name in (
        "resolve_product_inputs.py",
        "send_gemini_cli_prompt.py",
        "capture_capcut_result_audio.py",
        "prove_source_range.py",
        "upload_drive_local_file.py",
        "purge_local_working_media.py",
    ):
        relative = f".cursor/skills/produce-tiktok-product-video-portable/scripts/{name}"
        if not git_tracks(REPO, relative):
            raise FileNotFoundError(f"refusing untracked legacy helper: {relative}")
        src = REPO / relative
        dest = helper_dir / name
        dest.symlink_to(src)
    config = tmp / "config"
    config.mkdir()
    settings = {
        "schema_version": "1",
        "status": "active",
        "product_model": "AN-S999",
        "cta": {"text": "下からチェック！", "literal_match_required": True},
        "product_information": ["車内の日差しを遮るサンシェード"],
        "product_appeal_points": ["装着が簡単", "使わないときは畳んで収納できる"],
    }
    (config / "product_video_settings_AN-S999.v1.json").write_text(
        json.dumps(settings, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    materials = tmp / ".runtime" / "product-video-inputs" / "AN-S999_コピー"
    materials.mkdir(parents=True)
    (materials / "clip.mov").write_bytes(b"not-a-real-video")
    return tmp


def seed_state(root: Path, case_id: str, stage: str, completed: list[str], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    (root / "outputs" / case_id).mkdir(parents=True, exist_ok=True)
    state = empty_state(case_id, "AN-S999")
    state["current_stage"] = stage
    state["completed_stages"] = completed
    if extra:
        state.update(extra)
    save_state(root, state)
    return load_state(root, case_id)


def visual(subject: str, framing: str, location: str) -> dict[str, str]:
    return {
        "subject": subject,
        "framing": framing,
        "camera_distance": framing,
        "camera_angle": "eye",
        "location": location,
        "action": subject,
        "interaction": "hands" if subject == "hands" else "product",
        "movement": "static",
    }


def test_parser() -> None:
    for count in (3, 4, 5):
        parsed = parse_gemini_scripts(sample_scripts(count))
        check(f"parser-{count}", parsed.get("status") == "OK" and parsed.get("variant_count") == count)
        if parsed.get("status") == "OK":
            first = parsed["variants"][0]
            check(f"parser-{count}-situation", first["cuts"][0]["situation"].startswith("車内"))
    two = parse_gemini_scripts(sample_scripts(2))
    check("parser-reject-2", two.get("status") == "HOLD")
    six = parse_gemini_scripts(sample_scripts(6))
    check("parser-reject-6", six.get("status") == "HOLD")


def test_approval_and_fidelity() -> None:
    state = {"script_variant_ids": [1, 2, 3]}
    ok = bind_script_selection("案2で台本OK", state)
    check("approval-explicit", ok.get("status") == "OK" and ok.get("variant_id") == 2)
    for bad in ("台本OK", "案2でOK", "進めてください", "案2で台本をお願い", "粗編集OK", "完成・書き出しOK"):
        result = bind_script_selection(bad, state)
        check(f"approval-reject-{bad}", result.get("status") == "HOLD")
    line = "車、サウナすぎん？"
    check("fidelity-equal", assert_immutable(line, line, role="tts").get("status") == "OK")
    check(
        "fidelity-no-shorten",
        assert_immutable(line, "車、サウナ？", role="tts").get("hold") == "HOLD_SCRIPT_LINE_IMMUTABLE",
    )
    check(
        "fidelity-no-punct",
        assert_immutable(line, "車、サウナすぎん。", role="tts").get("status") != "OK",
    )


def test_speed_and_tts(root: Path) -> None:
    check("speed-constant", narration_speed() == 1.2 == NARRATION_SPEED)
    clip = record_clip(cut_id="c1", line="a", audio_path="/tmp/a.mp3", duration_seconds=3.2)
    check("duration-recorded", clip.get("duration_seconds") == 3.2 and clip.get("speed") == 1.2)
    bad_speed = record_clip(cut_id="c1", line="a", audio_path="/tmp/a.mp3", duration_seconds=3.2, speed=1.0)
    check("speed-reject-1.0", bad_speed.get("hold") == "HOLD_NARRATION_SPEED")
    frozen = "そんな時はこのサンシェード。"
    ready = gate_tts_generate(
        root,
        {
            "field_id": "capcut-tts-textarea",
            "field_identified": True,
            "full_replace_applied": True,
            "textarea_readback": frozen,
            "readback_source": "actual_textarea_value",
            "frozen_line": frozen,
            "input_tool_success": True,
            "generation_count_for_cut": 0,
        },
        frozen,
    )
    check("tts-exact-allows", ready.get("generate") is True)
    blocked = gate_tts_generate(
        root,
        {
            "field_id": "capcut-tts-textarea",
            "field_identified": True,
            "full_replace_applied": True,
            "textarea_readback": "前回の文" + frozen,
            "readback_source": "actual_textarea_value",
            "frozen_line": frozen,
            "previous_line": "前回の文",
            "input_tool_success": True,
            "generation_count_for_cut": 0,
        },
        frozen,
    )
    check("tts-mismatch-blocks", blocked.get("generate") is False)


class FakeTtsField:
    def __init__(self, *, prefix_on_write: list[str] | None = None, after_clear: str = "") -> None:
        self.field_id = "capcut-tts-textarea"
        self.value = "STALE_LEFTOVER"
        self.writes = 0
        self.clears = 0
        self.generation_count = 0
        self.prefix_on_write = prefix_on_write or [""]
        self.after_clear = after_clear

    def identify(self) -> str:
        return self.field_id

    def clear(self) -> bool:
        self.clears += 1
        self.value = self.after_clear
        return True

    def write(self, text: str) -> bool:
        prefix = self.prefix_on_write[min(self.writes, len(self.prefix_on_write) - 1)]
        self.writes += 1
        self.value = prefix + text
        return True

    def read_actual(self) -> str:
        return self.value


def test_tts_input_recovery(root: Path) -> None:
    frozen = "夏の車に乗った瞬間、地獄すぎない？"
    exact_record = {
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": frozen,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "input_tool_success": True,
        "generation_count_for_cut": 0,
    }
    check("tts-recovery-A-exact-generate", gate_tts_generate(root, exact_record, frozen).get("generate") is True)

    leading_nl = "\n" + frozen
    check(
        "tts-recovery-B-leading-newline-blocks",
        gate_tts_generate(
            root,
            {**exact_record, "textarea_readback": leading_nl},
            frozen,
        ).get("generate")
        is False,
    )
    diag_b = diagnose_mismatch(frozen, leading_nl)
    check("tts-recovery-B-extra-U+000A", (diag_b.get("extra_codepoint") or "").startswith("U+000A"))
    check("tts-recovery-B-repr", diag_b.get("actual_repr") == repr(leading_nl))

    zwsp = "\u200b" + frozen
    check(
        "tts-recovery-C-leading-zwsp-blocks",
        gate_tts_generate(root, {**exact_record, "textarea_readback": zwsp}, frozen).get("generate") is False,
    )
    diag_c = diagnose_mismatch(frozen, zwsp)
    check("tts-recovery-C-extra-U+200B", diag_c.get("extra_codepoint") == "U+200B ZERO WIDTH SPACE")

    trailing_nl = frozen + "\n"
    check(
        "tts-recovery-D-trailing-newline-blocks",
        gate_tts_generate(root, {**exact_record, "textarea_readback": trailing_nl}, frozen).get("generate") is False,
    )
    diag_d = diagnose_mismatch(frozen, trailing_nl)
    check("tts-recovery-D-extra-U+000A", (diag_d.get("extra_codepoint") or "").startswith("U+000A"))

    retry_field = FakeTtsField(prefix_on_write=["\n", ""])
    start_count = retry_field.generation_count
    prepared = prepare_tts_input(retry_field, frozen, generation_count_for_cut=start_count)
    check("tts-recovery-E-retry-then-match", prepared.get("exact_match") is True and prepared.get("input_attempts") == 2)
    check(
        "tts-recovery-F-retry-does-not-count-generation",
        prepared.get("generation_count_for_cut") == start_count == retry_field.generation_count == 0,
    )
    if prepared.get("exact_match") is True:
        gated = gate_tts_generate(root, prepared["record"], frozen)
        check("tts-recovery-E-generate-after-retry", gated.get("generate") is True)
    twice_bad = FakeTtsField(prefix_on_write=["\n", "\n"])
    held = prepare_tts_input(twice_bad, frozen, generation_count_for_cut=0)
    check("tts-recovery-second-mismatch-holds", held.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED" and held.get("generate") is False)
    first = compare_tts_readback(frozen, leading_nl, attempt=1, generation_count_for_cut=0)
    check("tts-recovery-attempt1-retry", first.get("retry") is True and first.get("generate") is False)
    second = compare_tts_readback(frozen, leading_nl, attempt=2, generation_count_for_cut=0)
    check("tts-recovery-attempt2-hold", second.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED" and second.get("retry") is False)

    check("tts-prewrite-empty-literal", is_pre_write_empty("") is True)
    check("tts-prewrite-empty-zwsp", is_pre_write_empty("\u200b") is True)
    check("tts-prewrite-not-newline", is_pre_write_empty("\n") is False)
    check("tts-prewrite-not-space", is_pre_write_empty(" ") is False)
    check("tts-prewrite-not-zwsp-plus-line", is_pre_write_empty("\u200b" + frozen) is False)

    empty_ok = FakeTtsField(after_clear="")
    prepared_a = prepare_tts_input(empty_ok, frozen, generation_count_for_cut=0)
    check("tts-prewrite-A-clear-empty-allows-write", prepared_a.get("exact_match") is True and empty_ok.writes == 1)

    zwsp_empty = FakeTtsField(after_clear="\u200b")
    prepared_b = prepare_tts_input(zwsp_empty, frozen, generation_count_for_cut=0)
    check("tts-prewrite-B-clear-zwsp-allows-write", prepared_b.get("exact_match") is True and zwsp_empty.writes == 1)

    nl_empty = FakeTtsField(after_clear="\n")
    held_c = prepare_tts_input(nl_empty, frozen, generation_count_for_cut=0)
    check(
        "tts-prewrite-C-clear-newline-holds",
        held_c.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED" and nl_empty.writes == 0,
    )

    space_empty = FakeTtsField(after_clear=" ")
    held_d = prepare_tts_input(space_empty, frozen, generation_count_for_cut=0)
    check(
        "tts-prewrite-D-clear-space-holds",
        held_d.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED" and space_empty.writes == 0,
    )

    leftover = FakeTtsField(after_clear=frozen)
    held_prev = prepare_tts_input(leftover, frozen, generation_count_for_cut=0)
    check("tts-prewrite-leftover-line-holds", held_prev.get("generate") is False and leftover.writes == 0)
    leftover_zwsp = FakeTtsField(after_clear="\u200b" + frozen)
    held_prev_zwsp = prepare_tts_input(leftover_zwsp, frozen, generation_count_for_cut=0)
    check("tts-prewrite-zwsp-plus-line-holds", held_prev_zwsp.get("generate") is False and leftover_zwsp.writes == 0)

    write_zwsp = FakeTtsField(prefix_on_write=["\u200b"], after_clear="\u200b")
    prepared_e = prepare_tts_input(write_zwsp, frozen, generation_count_for_cut=0)
    check("tts-prewrite-E-postwrite-leading-zwsp-mismatch", prepared_e.get("exact_match") is not True and prepared_e.get("generate") is False)
    if prepared_e.get("record"):
        check("tts-prewrite-E-must-not-gate-generate", False, "mismatch produced a prove record")
    else:
        check("tts-prewrite-E-no-prove-record", True)

    write_exact = FakeTtsField(after_clear="\u200b")
    prepared_f = prepare_tts_input(write_exact, frozen, generation_count_for_cut=0)
    check("tts-prewrite-F-postwrite-exact", prepared_f.get("exact_match") is True)
    if prepared_f.get("exact_match") is True:
        check("tts-prewrite-F-generate-allowed", gate_tts_generate(root, prepared_f["record"], frozen).get("generate") is True)


def test_assembly_and_variety() -> None:
    line = "これ一枚で全然違う。"
    previous = {"visual": visual("person", "wide", "car")}
    similar = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": "サンシェードを広げる手元",
        "scenario_tags": ["サンシェードを広げる手元"],
        "material_id": "similar",
        "visual": visual("person", "wide", "car"),
    }
    varied = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": "サンシェードを広げる手元",
        "scenario_tags": ["サンシェードを広げる手元"],
        "material_id": "varied",
        "visual": visual("hands", "close", "dash"),
    }
    invalid = {
        "semantic_valid": False,
        "supported_line": line,
        "situation": "無関係な風景",
        "material_id": "invalid",
        "visual": visual("hands", "close", "park"),
    }
    chosen = select_cut(
        [similar, varied],
        line=line,
        intended_scenario="サンシェードを広げる手元",
        duration_seconds=2.5,
        previous=previous,
    )
    check("variety-prefers-valid-alternative", chosen.get("selection", {}).get("material_id") == "varied")
    check("assembly-uses-duration", chosen.get("selection", {}).get("target_duration_seconds") == 2.5)
    unsafe = select_cut(
        [similar, invalid],
        line=line,
        intended_scenario="サンシェードを広げる手元",
        duration_seconds=2.5,
        previous=previous,
    )
    check("variety-never-invalid", unsafe.get("selection", {}).get("material_id") == "similar")
    script = {
        "cuts": [
            {"cut_id": "c1", "line": "車、サウナすぎん？", "situation": "車内でハンドルを握る人物"},
            {"cut_id": "c2", "line": line, "situation": "サンシェードを広げる手元"},
        ]
    }
    manifest = {
        "clips": [
            {"cut_id": "c1", "line": "車、サウナすぎん？", "audio_path": "a.mp3", "duration_seconds": 1.8},
            {"cut_id": "c2", "line": line, "audio_path": "b.mp3", "duration_seconds": 2.5},
        ]
    }
    c1 = {
        "semantic_valid": True,
        "supported_line": "車、サウナすぎん？",
        "situation": "車内でハンドルを握る人物",
        "scenario_tags": ["車内でハンドルを握る人物"],
        "material_id": "c1-person",
        "visual": visual("person", "wide", "car"),
    }
    plan = assemble_plan(
        script,
        manifest,
        {
            "c1": [c1],
            "c2": [similar, varied],
        },
    )
    check("scenario-survives", plan.get("status") == "OK" and plan["cuts"][1]["intended_scenario"] == "サンシェードを広げる手元")
    check("assembly-consumes-duration", plan["cuts"][0]["target_duration_seconds"] == 1.8)


def test_telop_and_rough() -> None:
    script = {"cuts": [{"cut_id": "c1", "line": "下からチェック！"}]}
    plan = {"cuts": [{"cut_id": "c1", "material_id": "cta"}]}
    manifest = {"clips": [{"cut_id": "c1", "audio_path": "c.mp3", "duration_seconds": 1.1}]}
    ok = build_rough_edit(
        script,
        plan,
        manifest,
        editor_project_identity="chatcut:proj-1",
        placed_telops=[{"cut_id": "c1", "text": "下からチェック！"}],
    )
    check("telop-exact", ok.get("usable_rough_edit") is True)
    check("no-ai-quality-review", ok.get("ai_visual_quality_review") is False)
    check("operator-message", ok.get("operator_message_ja") == OPERATOR_ROUGH_MESSAGE)
    bad = build_rough_edit(
        script,
        plan,
        manifest,
        editor_project_identity="chatcut:proj-1",
        placed_telops=[{"cut_id": "c1", "text": "下からチェック"}],
    )
    check("telop-mismatch-blocks", bad.get("hold") == "HOLD_SCRIPT_LINE_IMMUTABLE")


def test_delivery_gates() -> None:
    check("unknown-export-no-retry", may_start_job("unknown").get("retry") is False)
    check("pending-export-no-retry", may_start_job("in_progress").get("retry") is False)
    check("failed-may-start", may_start_job("failed").get("start") is True)
    incomplete = may_complete({"export_verified": True, "local_file_verified": True, "drive_uploaded": True})
    check("drive-required-before-complete", incomplete.get("hold") == "HOLD_DRIVE_READBACK_REQUIRED")
    complete_ok = may_complete(
        {
            "export_verified": True,
            "local_file_verified": True,
            "drive_uploaded": True,
            "drive_readback_verified": True,
        }
    )
    check("drive-allows-complete", complete_ok.get("status") == "OK")
    early = may_purge({"current_stage": "DELIVERY"}, {"drive_readback_verified": True})
    check("purge-not-before-complete", early.get("hold") == "HOLD_POST_COMPLETE_PURGE_NOT_DUE")
    after = may_purge({"current_stage": "COMPLETE"}, {"drive_readback_verified": True})
    check("purge-after-verified-delivery", after.get("purge") is True)


def test_dispatch_initial_entry(root: Path) -> None:
    """No case_id and no active case: first dispatch must create PREPARE without NameError."""
    outputs = root / "outputs"
    preexisting = [p.name for p in outputs.iterdir()] if outputs.is_dir() else []
    check("initial-entry-no-active-case", preexisting == [], str(preexisting))
    try:
        first = dispatch(root, product_model="AN-S999")
    except Exception as exc:  # noqa: BLE001 - this regression was a NameError
        check("initial-entry-no-exception", False, f"{type(exc).__name__}: {exc}")
        return
    check("initial-entry-no-exception", True)
    check("initial-entry-action", first.get("action") == "run_skill")
    check("initial-entry-skill", first.get("skill") == "product-video-prepare")
    check("initial-entry-stage", first.get("stage") == "PREPARE")
    case_id = first.get("case_id")
    check(
        "initial-entry-case-created",
        isinstance(case_id, str) and str(case_id).startswith("pv-AN-S999-"),
        str(case_id),
    )
    state_file = root / "outputs" / str(case_id) / "workflow-state.json"
    check("initial-entry-state-exists", state_file.is_file())
    cases = sorted(p.name for p in outputs.iterdir() if p.is_dir()) if outputs.is_dir() else []
    check("initial-entry-one-case", cases == [case_id], str(cases))
    try:
        second = dispatch(root, product_model="AN-S999")
    except Exception as exc:  # noqa: BLE001
        check("initial-entry-reuse-no-exception", False, f"{type(exc).__name__}: {exc}")
        return
    check("initial-entry-reuse-no-exception", True)
    check("initial-entry-reuse-same-case", second.get("case_id") == case_id, str(second.get("case_id")))
    check(
        "initial-entry-reuse-prepare",
        second.get("action") == "run_skill"
        and second.get("skill") == "product-video-prepare"
        and second.get("stage") == "PREPARE",
    )
    cases_after = sorted(p.name for p in outputs.iterdir() if p.is_dir()) if outputs.is_dir() else []
    check("initial-entry-no-duplicate-case", cases_after == [case_id], str(cases_after))


def test_dispatch_resume(root: Path) -> None:
    case_id = "pv-AN-S999-test"
    seed_state(root, case_id, "PREPARE", [])
    first = dispatch(root, case_id=case_id)
    check("dispatch-prepare", first.get("skill") == "product-video-prepare" and first.get("ask_continue") is False)
    finish_prepare_missing = finish_prepare(root, case_id)
    check("prepare-needs-inputs", finish_prepare_missing.get("status") == "HOLD")
    inputs = build_product_inputs(
        {"product_model": "AN-S999", "cta": {"text": "下からチェック！"}},
        verified_facts=["車内の日差しを遮るサンシェード"],
        appeal_points=["装着が簡単"],
        user_campaign_focus="夏の車内",
    )
    check("no-invented-claims", "99%" not in inputs.get("product_information", "") and inputs.get("invented_claims") is False)
    (root / "outputs" / case_id / "product-inputs.json").write_text(
        json.dumps(inputs, ensure_ascii=False),
        encoding="utf-8",
    )
    prepared = finish_prepare(root, case_id)
    check("prepare-advances", prepared.get("current_stage") == "SCRIPT")
    again = dispatch(root, case_id=case_id)
    check("resume-skips-prepare", again.get("skill") == "product-video-script")
    try:
        complete_stage(root, load_state(root, case_id), "PREPARE", {"status": "OK"})
        check("no-duplicate-prepare", False)
    except ValueError:
        check("no-duplicate-prepare", True)
    (root / "outputs" / case_id / "gemini-output.txt").write_text(sample_scripts(3), encoding="utf-8")
    stored = accept_gemini_output(root, case_id, sample_scripts(3))
    check("script-stops-for-selection", stored.get("current_stage") == "SCRIPT_SELECTION")
    waiting = dispatch(root, case_id=case_id, utterance="進めてください")
    check("invalid-does-not-approve", waiting.get("reason") == "waiting_script_selection")
    check("script-not-rerun", waiting.get("skill") is None)
    frozen = dispatch(root, case_id=case_id, utterance="案2で台本OK")
    check("explicit-selection-binds", frozen.get("skill") == "product-video-narration")
    state = load_state(root, case_id)
    check("variant-frozen", state.get("selected_script_variant") == 2)
    clips = [
        record_clip(cut_id="c1", line="車、サウナすぎん？2", audio_path="a.mp3", duration_seconds=1.7),
        record_clip(cut_id="c2", line="これ一枚で全然違う。", audio_path="b.mp3", duration_seconds=2.1),
    ]
    write_manifest(root, case_id, clips)
    state["narration_manifest_path"] = str(root / "outputs" / case_id / "narration-manifest.json")
    save_state(root, state)
    narrated = complete_stage(root, load_state(root, case_id), "NARRATION", {"clip_count": 2})
    check("narration-to-assembly", narrated.get("current_stage") == "ASSEMBLY")
    assembled = complete_stage(root, load_state(root, case_id), "ASSEMBLY", {"cuts": 2})
    check("assembly-to-rough", assembled.get("current_stage") == "ROUGH_EDIT")
    rough = dispatch(root, case_id=case_id)
    check("dispatch-rough", rough.get("skill") == "product-video-rough-edit")
    waiting_op = complete_stage(root, load_state(root, case_id), "ROUGH_EDIT", {"usable_rough_edit": True})
    check("rough-to-waiting", waiting_op.get("current_stage") == "WAITING_FOR_OPERATOR")
    stop = dispatch(root, case_id=case_id, utterance="粗編集OK")
    check("no-rough-ok", stop.get("reason") == "waiting_for_operator")
    check("waiting-message", OPERATOR_ROUGH_MESSAGE.splitlines()[0] in (stop.get("message_ja") or ""))
    denied = dispatch(root, case_id=case_id, utterance="完成・書き出しOK")
    check("old-final-ok-rejected", denied.get("reason") == "waiting_for_operator")
    delivery = dispatch(root, case_id=case_id, utterance=DELIVERY_APPROVAL)
    check("delivery-requires-phrase", delivery.get("skill") == "product-video-delivery")


def test_create_case(root: Path) -> None:
    created = create_new_case(
        root,
        "AN-S999",
        "夏の車内",
        verified_facts=["車内の日差しを遮るサンシェード"],
        appeal_points=["装着が簡単"],
    )
    check("create-isolated-case", created.get("status") == "OK" and str(created.get("case_id", "")).startswith("pv-AN-S999-"))
    if created.get("status") == "OK":
        state = load_state(root, created["case_id"])
        check("new-case-at-prepare", state["current_stage"] == "PREPARE")
        check("case-state-exists", (root / "outputs" / created["case_id"] / "workflow-state.json").is_file())
        check("compact-state", not validate_compact(state))


def test_prompt_template() -> None:
    template = load_template(REPO)
    prompt = render_script_prompt(
        template,
        product_information="- 車内の日差しを遮るサンシェード",
        product_appeal_points="- 装着が簡単",
        user_campaign_focus="夏の車内",
    )
    check("prompt-has-facts", "車内の日差しを遮るサンシェード" in prompt)
    check("prompt-has-campaign", "夏の車内" in prompt)
    check("prompt-keeps-1.2", "1.2倍速" in prompt)
    check("prompt-asks-3-to-5", "3〜5パターン" in prompt)
    check("prompt-bans-model-in-line", "識別番号はセリフに入れない" in prompt)
    check("prompt-bans-model-in-cta", "CTAにも型番を入れない" in prompt)
    check("prompt-short-line-range", "12〜22文字" in prompt)
    check("prompt-short-line-cap", "25文字を大きく超えない" in prompt)


def test_runtime_path() -> None:
    names = (
        "product-video",
        "product-video-prepare",
        "product-video-script",
        "product-video-narration",
        "product-video-assembly",
        "product-video-rough-edit",
        "product-video-delivery",
    )
    skills_root = REPO / ".cursor" / "skills"
    for name in names:
        skill_md = skills_root / name / "SKILL.md" if name != "product-video" else skills_root / "product-video" / "SKILL.md"
        # product-video-prepare lives beside product-video
        skill_md = skills_root / name / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        check(f"skill-exists-{name}", skill_md.is_file() and len(text.splitlines()) < 500)
        check(
            f"no-old-skill-md-{name}",
            "produce-tiktok-product-video-portable/SKILL.md" not in text
            and "produce-tiktok-product-video-v3/SKILL.md" not in text,
        )
        check(f"no-craft-{name}", "validate_craft_quality.py" not in text and "select_common_tts_speed.py" not in text)
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    check("agents-entry-product-video", "invoke `/product-video`" in agents)
    check("agents-not-old-entry", "invoke `/produce-tiktok-product-video-portable`" not in agents)
    for path in SCRIPTS.glob("*.py"):
        if path.name in {"constants.py", "run_self_test.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        check(f"no-old-runtime-{path.name}", all(marker not in text for marker in OLD_SKILL_MARKERS))
    check("entry-is-product-video", (skills_root / "product-video" / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: product-video"))


def test_git_tracked_helpers() -> None:
    owned = helper_relpath("prove_tts_textarea")
    check("tts-gate-owned-path", owned == ".cursor/skills/product-video/scripts/prove_tts_textarea.py")
    check("tts-gate-not-legacy-untracked", "produce-tiktok-product-video-portable" not in owned)
    resolved = helper_path(REPO, "prove_tts_textarea")
    check("tts-gate-resolves-owned", resolved == REPO / owned)
    prepare_owned = helper_relpath("prepare_tts_field")
    check("tts-prepare-owned-path", prepare_owned == ".cursor/skills/product-video/scripts/prepare_tts_field.py")
    check("tts-prepare-resolves-owned", helper_path(REPO, "prepare_tts_field") == REPO / prepare_owned)
    missing = missing_git_tracked_helpers(REPO)
    check("runtime-helpers-git-tracked", missing == [], str(missing))
    skill_py = re.compile(r"\$\{PROJECT_ROOT\}/(\.cursor/skills/[^\s`\"']+\.py)")
    skills_root = REPO / ".cursor" / "skills"
    for name in (
        "product-video",
        "product-video-prepare",
        "product-video-script",
        "product-video-narration",
        "product-video-assembly",
        "product-video-rough-edit",
        "product-video-delivery",
    ):
        text = (skills_root / name / "SKILL.md").read_text(encoding="utf-8")
        for relative in skill_py.findall(text):
            check(
                f"skill-helper-tracked-{name}:{Path(relative).name}",
                git_tracks(REPO, relative),
                relative,
            )
    portable_untracked = (
        REPO / ".cursor" / "skills" / "produce-tiktok-product-video-portable" / "scripts" / "prove_tts_textarea.py"
    )
    check(
        "legacy-untracked-tts-not-required",
        not git_tracks(
            REPO,
            ".cursor/skills/produce-tiktok-product-video-portable/scripts/prove_tts_textarea.py",
        ),
    )
    check("owned-tts-exists", (REPO / owned).is_file())
    narration_skill = (skills_root / "product-video-narration" / "SKILL.md").read_text(encoding="utf-8")
    check("narration-skill-uses-owned-tts", "product-video/scripts/prove_tts_textarea.py" in narration_skill)
    check("narration-skill-uses-prepare-tts", "product-video/scripts/prepare_tts_field.py" in narration_skill)
    check(
        "narration-skill-no-legacy-tts",
        "produce-tiktok-product-video-portable/scripts/prove_tts_textarea.py" not in narration_skill,
    )
    if portable_untracked.is_file():
        check("does-not-use-untracked-copy-as-runtime", resolved != portable_untracked.resolve())


def test_forbidden_state() -> None:
    errors = validate_compact({"schema": "x", "base64": "AAAA", "current_stage": "PREPARE"})
    check("state-rejects-base64-key", bool(errors))
    errors2 = validate_compact({"image": "x"})
    check("state-rejects-image-key", bool(errors2))


def main() -> int:
    print(f"REPO {REPO}")
    test_parser()
    test_approval_and_fidelity()
    test_prompt_template()
    test_assembly_and_variety()
    test_telop_and_rough()
    test_delivery_gates()
    test_runtime_path()
    test_git_tracked_helpers()
    test_forbidden_state()
    scratch = SCRIPTS / "_scratch"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    try:
        root = fake_project(scratch)
        test_speed_and_tts(root)
        test_tts_input_recovery(root)
        test_create_case(root)
        test_dispatch_resume(root)
        entry_root = fake_project(scratch / "initial-entry")
        test_dispatch_initial_entry(entry_root)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if FAILURES:
        print("SELF-TEST FAILED: " + ", ".join(FAILURES))
        return 1
    print("SELF-TEST PASSED: product-video")
    print("LIVE_UNVERIFIED: Gemini CLI, CapCut TTS, ChatCut edit, export, Drive upload/read-back, purge execute")
    print("NO_PRODUCTION_VIDEO_CREATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
