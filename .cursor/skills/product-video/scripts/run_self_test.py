#!/usr/bin/env python3
"""Local tests for /product-video. No live production, Gemini, CapCut, or Drive."""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPTS))

from assembly import assemble_plan, select_cut  # noqa: E402
from bind_script_selection import bind_script_selection  # noqa: E402
from classify_capcut_credit import classify_capcut_credit  # noqa: E402
from constants import (  # noqa: E402
    DELIVERY_APPROVAL,
    HOLD_CAPCUT_CREDIT_UNVERIFIED,
    HOLD_CAPCUT_NEW_PURCHASE_REQUIRED,
    HOLD_INPUT_MATERIALS_REQUIRED,
    HOLD_MATERIAL_VIDEO_REQUIRED,
    NARRATION_SPEED,
    OLD_SKILL_MARKERS,
    OPERATOR_ROUGH_MESSAGE,
    PERSISTENT_SHARED_INPUT_RELATIVE,
)
from delivery import may_complete, may_purge, may_start_job  # noqa: E402
from dispatch import dispatch  # noqa: E402
from narration import gate_tts_generate, narration_speed, prepare_tts_input, record_clip, write_manifest  # noqa: E402
from prove_tts_speed import planned_editorial_duration, prove_editorial_timing, prove_tts_speed  # noqa: E402
from rough_edit import build_rough_edit, prove_placed_narration_clip  # noqa: E402
from resolve_tts_text import compare_effective_to_frozen, resolve_effective_tts_text  # noqa: E402
from tts_attempts import generation_count_for_cut, load_attempts, may_generate_cut, record_generation_attempt  # noqa: E402
from parse_gemini_scripts import parse_gemini_scripts  # noqa: E402
from paths import git_tracks, helper_path, helper_relpath, missing_git_tracked_helpers  # noqa: E402
from prepare import build_product_inputs, create_new_case, finish_prepare  # noqa: E402
from preserve_shared_inputs import (  # noqa: E402
    PERSISTENT_SKIP_REASON,
    is_persistent_shared_input_path,
    planned_hits_persistent_shared_inputs,
)
from prove_material_videos import prove_material_videos  # noqa: E402
from prepare_tts_field import compare_tts_readback, diagnose_mismatch, is_pre_write_empty  # noqa: E402
from render_script_prompt import load_template, render_script_prompt  # noqa: E402
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
    shutil.copy(
        REPO / ".cursor" / "skills" / "product-video" / "scripts" / "resolve_tts_text.py",
        owned_scripts / "resolve_tts_text.py",
    )
    shutil.copy(
        REPO / ".cursor" / "skills" / "product-video" / "scripts" / "prove_tts_speed.py",
        owned_scripts / "prove_tts_speed.py",
    )
    shutil.copy(
        REPO / ".cursor" / "skills" / "product-video" / "scripts" / "tts_attempts.py",
        owned_scripts / "tts_attempts.py",
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
    six_to_five = planned_editorial_duration(6.0, 1.2)
    check(
        "planned-6s-at-1.2-is-5s",
        six_to_five.get("status") == "OK" and six_to_five.get("planned_duration_seconds") == 5.0,
    )
    clip = record_clip(cut_id="c1", line="a", audio_path="/tmp/a.mp3", source_duration_seconds=6.0)
    check(
        "source-and-planned-distinguished",
        clip.get("source_duration_seconds") == 6.0
        and clip.get("planned_duration_seconds") == 5.0
        and clip.get("editor_playback_rate") == 1.2
        and clip.get("source_already_accelerated") is False
        and "duration_seconds" not in clip,
    )
    pre_accelerated = record_clip(
        cut_id="c1",
        line="a",
        audio_path="/tmp/a.mp3",
        source_duration_seconds=6.0,
        source_already_accelerated=True,
    )
    check("source-not-pre-accelerated", pre_accelerated.get("hold") == "HOLD_NARRATION_SPEED")
    bad_speed = record_clip(cut_id="c1", line="a", audio_path="/tmp/a.mp3", source_duration_seconds=6.0, speed=1.0)
    check("speed-reject-1.0", bad_speed.get("hold") == "HOLD_NARRATION_SPEED")
    copied_plan = prove_editorial_timing(
        {
            **clip,
            "playback_rate": 1.2,
            "speed_readback_source": "chatcut_item",
            "measured_duration_seconds": 5.0,
            "measured_duration_source": "planned",
        }
    )
    check("measured-not-copied-from-plan", copied_plan.get("status") == "HOLD")
    measured = prove_editorial_timing(
        {
            **clip,
            "playback_rate": 1.2,
            "speed_readback_source": "chatcut_item",
            "measured_duration_seconds": 5.0,
            "measured_duration_source": "chatcut_item",
        }
    )
    check(
        "measured-from-chatcut-item",
        measured.get("status") == "OK"
        and measured.get("planned_duration_seconds") == 5.0
        and measured.get("measured_duration_seconds") == 5.0
        and measured.get("durations_distinguished") is True,
    )
    placed = prove_placed_narration_clip(
        {
            **clip,
            "playback_rate": 1.2,
            "speed_readback_source": "chatcut_item",
            "measured_duration_seconds": 5.0,
            "measured_duration_source": "chatcut_item",
        }
    )
    check("chatcut-playbackRate-1.2-required", placed.get("status") == "OK")
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
        gated = gate_tts_generate(
            root,
            {**prepared["record"]},
            frozen,
        )
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
        check(
            "tts-prewrite-F-generate-allowed",
            gate_tts_generate(
                root,
                {**prepared_f["record"]},
                frozen,
            ).get("generate")
            is True,
        )


def test_tts_runtime_gaps(root: Path) -> None:
    frozen = "夏の車に乗った瞬間、地獄すぎない？"
    case_id = "pv-AN-S999-tts-attempts"
    (root / "outputs" / case_id / "tts").mkdir(parents=True, exist_ok=True)
    base_record = {
        "field_id": "capcut-tts-contenteditable",
        "field_identified": True,
        "full_replace_applied": True,
        "frozen_line": frozen,
        "input_tool_success": True,
        "generation_count_for_cut": 0,
    }

    html_obs = {
        "inner_text": frozen + "\u200b",
        "document_html_line_text": frozen,
        "proof_source": "document_html_line_text",
    }
    html_resolved = resolve_effective_tts_text(html_obs)
    check(
        "tts-gap-A-document-html-not-proof",
        html_resolved.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED"
        and html_resolved.get("effective_tts_text") is None
        and html_resolved.get("rejected_proof_source") == "document_html_line_text",
    )
    html_fallback = resolve_effective_tts_text(
        {"inner_text": frozen + "\u200b", "document_html_line_text": frozen}
    )
    check(
        "tts-gap-A-does-not-use-matching-document-text",
        html_fallback.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED"
        and html_fallback.get("effective_tts_text") is None
        and html_fallback.get("ignored_document_html") is True,
    )
    html_gate = gate_tts_generate(
        root,
        {**base_record, "textarea_readback": frozen, "readback_source": "document_html_line_text"},
        frozen,
    )
    check(
        "tts-gap-A-gate-rejects-document-html",
        html_gate.get("generate") is False and html_gate.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED",
    )

    sentinel_obs = {
        "inner_text": frozen + "\u200b",
        "dom_nodes": [
            {"text": frozen, "kind": "user_authored"},
            {
                "text": "\u200b",
                "kind": "structural_sentinel",
                "independent": True,
                "evidence": "CapCut editor-kit empty-line marker leaf",
            },
        ],
    }
    sentinel = compare_effective_to_frozen(frozen, sentinel_obs)
    check(
        "tts-gap-B-sentinel-nodes-pass",
        sentinel.get("exact_match") is True
        and sentinel.get("effective_tts_text") == frozen
        and sentinel.get("readback_source") == "user_authored_dom_nodes",
    )
    sentinel_gate = gate_tts_generate(root, {**base_record, "observation": sentinel_obs}, frozen)
    check("tts-gap-B-gate-generate", sentinel_gate.get("generate") is True)

    unknown = resolve_effective_tts_text(
        {
            "inner_text": frozen + "\u200b",
            "dom_nodes": [
                {"text": frozen + "\u200b", "kind": "unknown"},
            ],
        }
    )
    check(
        "tts-gap-C-unclassified-zwsp-holds",
        unknown.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED" and unknown.get("generate") is False,
    )
    inner_only = resolve_effective_tts_text({"inner_text": frozen + "\u200b"})
    check(
        "tts-gap-C-innertext-zwsp-without-nodes-holds",
        inner_only.get("hold") == "HOLD_TTS_INPUT_FIELD_UNVERIFIED",
    )

    setter_only = prove_tts_speed({"on_speed_change_called": True, "setter_succeeded": True})
    check(
        "tts-gap-D-setter-is-not-speed-proof",
        setter_only.get("hold") == "HOLD_TTS_SPEED_UNVERIFIED" and setter_only.get("speed_ok") is not True,
    )
    speed_missing = gate_tts_generate(
        root,
        {
            **base_record,
            "textarea_readback": frozen,
            "readback_source": "actual_textarea_value",
            "actual_speed": None,
        },
        frozen,
    )
    check(
        "tts-gap-D-generate-without-capcut-speed",
        speed_missing.get("generate") is True and speed_missing.get("hold") is None,
    )

    capcut_speed = prove_tts_speed({"actual_speed": 1.2, "speed_readback_source": "ui"})
    check("tts-gap-E-capcut-actual-speed-not-clip-proof", capcut_speed.get("speed_ok") is not True)
    speed_ok = prove_tts_speed({"playback_rate": 1.2, "speed_readback_source": "chatcut_item"})
    check("tts-gap-E-chatcut-playbackRate-1.2-passes", speed_ok.get("speed_ok") is True and speed_ok.get("playback_rate") == 1.2)

    failed = record_generation_attempt(
        root,
        case_id,
        "c1",
        outcome="failure",
        adopted_audio=True,
        hold_code="HOLD_CAPCUT_TTS_GENERATE_FAILED",
    )
    stored = load_attempts(root, case_id)
    check(
        "tts-gap-F-failure-increments-without-audio",
        failed.get("generation_count_for_cut") == 1
        and failed.get("adopted_audio") is False
        and generation_count_for_cut(stored, "c1") == 1
        and stored["cuts"]["c1"]["last_outcome"] == "failure",
    )

    resumed = may_generate_cut(stored, "c1")
    check(
        "tts-gap-G-resume-starts-at-count-1",
        resumed.get("generate") is True
        and resumed.get("generation_count_for_cut") == 1
        and resumed.get("next_attempt_number") == 2,
    )
    second_allowed = gate_tts_generate(
        root,
        {
            **base_record,
            "textarea_readback": frozen,
            "readback_source": "actual_textarea_value",
            "generation_count_for_cut": 1,
        },
        frozen,
    )
    check("tts-gap-G-second-generate-allowed", second_allowed.get("generate") is True)
    second_fail = record_generation_attempt(root, case_id, "c1", outcome="failure")
    check("tts-gap-G-second-failure-count-2", second_fail.get("generation_count_for_cut") == 2)

    blocked = may_generate_cut(load_attempts(root, case_id), "c1")
    check(
        "tts-gap-H-third-may-generate-forbidden",
        blocked.get("hold") == "HOLD_TTS_ALLOWANCE_EXHAUSTED" and blocked.get("generate") is False,
    )
    third_record = record_generation_attempt(root, case_id, "c1", outcome="failure")
    check(
        "tts-gap-H-third-record-forbidden",
        third_record.get("hold") == "HOLD_TTS_ALLOWANCE_EXHAUSTED"
        and generation_count_for_cut(load_attempts(root, case_id), "c1") == 2,
    )
    third_gate = gate_tts_generate(
        root,
        {
            **base_record,
            "textarea_readback": frozen,
            "readback_source": "actual_textarea_value",
            "generation_count_for_cut": 2,
        },
        frozen,
    )
    check("tts-gap-H-third-generate-forbidden", third_gate.get("hold") == "HOLD_TTS_ALLOWANCE_EXHAUSTED")


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
            {"cut_id": "c1", "line": "車、サウナすぎん？", "audio_path": "a.mp3", "source_duration_seconds": 6.0, "editor_playback_rate": 1.2, "planned_duration_seconds": 5.0, "source_already_accelerated": False},
            {"cut_id": "c2", "line": line, "audio_path": "b.mp3", "source_duration_seconds": 3.0, "editor_playback_rate": 1.2, "planned_duration_seconds": 2.5, "source_already_accelerated": False},
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
    check("assembly-consumes-planned-duration", plan["cuts"][0]["target_duration_seconds"] == 5.0)
    source_as_cut = assemble_plan(
        {"cuts": [{"cut_id": "c1", "line": "車、サウナすぎん？", "situation": "車内でハンドルを握る人物"}]},
        {"clips": [{"cut_id": "c1", "line": "車、サウナすぎん？", "audio_path": "a.mp3", "duration_seconds": 6.0}]},
        {"c1": [c1]},
    )
    check("assembly-rejects-source-as-cut-duration", source_as_cut.get("status") == "HOLD")


def test_telop_and_rough() -> None:
    script = {"cuts": [{"cut_id": "c1", "line": "下からチェック！"}]}
    plan = {"cuts": [{"cut_id": "c1", "material_id": "cta"}]}
    manifest = {"clips": [{"cut_id": "c1", "audio_path": "c.mp3", "source_duration_seconds": 1.32, "editor_playback_rate": 1.2, "planned_duration_seconds": 1.1, "source_already_accelerated": False}]}
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
    materials = root / ".runtime" / "product-video-inputs" / "AN-S999_コピー"
    seed_state(root, case_id, "PREPARE", [], extra={"material_root": str(materials)})
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
    prepare_receipt = json.loads(
        (root / "outputs" / case_id / "receipts" / "prepare.json").read_text(encoding="utf-8")
    )
    check(
        "material-F-prepare-receipt-video-count",
        int(prepare_receipt.get("result", {}).get("material_video_count") or 0) >= 1,
    )
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
        record_clip(cut_id="c1", line="車、サウナすぎん？2", audio_path="a.mp3", source_duration_seconds=2.04),
        record_clip(cut_id="c2", line="これ一枚で全然違う。", audio_path="b.mp3", source_duration_seconds=2.52),
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
        draft = json.loads(
            (root / "outputs" / created["case_id"] / "receipts" / "prepare_draft.json").read_text(encoding="utf-8")
        )
        check(
            "material-F-draft-video-count",
            int(draft.get("result", {}).get("material_video_count") or 0) >= 1,
        )


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
    for name, rel in (
        ("resolve_tts_text", ".cursor/skills/product-video/scripts/resolve_tts_text.py"),
        ("prove_tts_speed", ".cursor/skills/product-video/scripts/prove_tts_speed.py"),
        ("tts_attempts", ".cursor/skills/product-video/scripts/tts_attempts.py"),
        ("prove_material_videos", ".cursor/skills/product-video/scripts/prove_material_videos.py"),
        ("classify_capcut_credit", ".cursor/skills/product-video/scripts/classify_capcut_credit.py"),
        ("preserve_shared_inputs", ".cursor/skills/product-video/scripts/preserve_shared_inputs.py"),
    ):
        check(f"tts-{name}-owned-path", helper_relpath(name) == rel)
        check(f"tts-{name}-resolves-owned", helper_path(REPO, name) == REPO / rel)
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
    check("narration-skill-uses-resolve-tts", "product-video/scripts/resolve_tts_text.py" in narration_skill)
    check("narration-skill-uses-speed-proof", "product-video/scripts/prove_tts_speed.py" in narration_skill)
    check("narration-skill-no-capcut-actual-speed-gate", "actual_speed == 1.2" not in narration_skill)
    rough_skill = (skills_root / "product-video-rough-edit" / "SKILL.md").read_text(encoding="utf-8")
    check("rough-skill-uses-chatcut-playbackRate", "playbackRate" in rough_skill and "prove_tts_speed.py" in rough_skill)
    check("narration-skill-uses-attempts", "product-video/scripts/tts_attempts.py" in narration_skill)
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


def test_material_video_preflight() -> None:
    missing = prove_material_videos(Path("/tmp/product-video-missing-material-root-does-not-exist"))
    check("material-A-missing-root-holds", missing.get("status") == "HOLD")
    check("material-A-missing-root-code", missing.get("hold") == HOLD_INPUT_MATERIALS_REQUIRED)
    with tempfile.TemporaryDirectory() as raw:
        empty = Path(raw) / "empty"
        empty.mkdir()
        held_empty = prove_material_videos(empty)
        check("material-B-empty-dir", held_empty.get("hold") == HOLD_MATERIAL_VIDEO_REQUIRED)
        check("material-B-video-count-0", held_empty.get("video_count") == 0)
        check("material-B-reports-root", held_empty.get("material_root") == empty.as_posix())

        cats = Path(raw) / "categories"
        (cats / "設置風景").mkdir(parents=True)
        (cats / "車内暑い").mkdir()
        held_cats = prove_material_videos(cats)
        check("material-C-category-dirs-only", held_cats.get("status") == "HOLD" and held_cats.get("video_count") == 0)

        zero = Path(raw) / "zero"
        zero.mkdir()
        (zero / "clip.mp4").write_bytes(b"")
        held_zero = prove_material_videos(zero)
        check("material-D-zero-byte-mp4", held_zero.get("hold") == HOLD_MATERIAL_VIDEO_REQUIRED)

        nested = Path(raw) / "nested"
        (nested / "設置風景").mkdir(parents=True)
        (nested / "設置風景" / "IMG_3894.MOV").write_bytes(b"not-a-real-video")
        ok = prove_material_videos(nested)
        check(
            "material-E-subdir-MOV",
            ok.get("status") == "OK" and int(ok.get("material_video_count") or 0) >= 1,
        )


def existing_credit_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "title": "Credits will be consumed",
        "credits_required": 10,
        "buttons": ["Cancel", "Got it"],
        "pro_subscription": False,
        "free_trial": False,
        "purchase_credits": False,
        "auto_reload": False,
        "new_payment": False,
        "plan_change": False,
        "monthly_or_annual_price": False,
        "payment_form": False,
        "body_contains_pro": False,
    }
    record.update(overrides)
    return record


def test_capcut_credit_policy() -> None:
    allowed = classify_capcut_credit(existing_credit_record())
    check("credit-H-existing-balance-allows-got-it", allowed.get("approve_got_it") is True)
    pro_in_body = classify_capcut_credit(existing_credit_record(body_contains_pro=True))
    check(
        "credit-H-pro-word-alone-is-not-hold",
        pro_in_body.get("approve_got_it") is True,
    )
    new_pro = classify_capcut_credit(existing_credit_record(pro_subscription=True))
    check(
        "credit-H-pro-contract-holds",
        new_pro.get("hold") == HOLD_CAPCUT_NEW_PURCHASE_REQUIRED and new_pro.get("approve_got_it") is False,
    )
    purchase = classify_capcut_credit(existing_credit_record(purchase_credits=True))
    check("credit-H-extra-purchase-holds", purchase.get("hold") == HOLD_CAPCUT_NEW_PURCHASE_REQUIRED)
    ambiguous = classify_capcut_credit({"title": "Credits will be consumed", "body_contains_pro": True})
    check("credit-H-ambiguous-holds", ambiguous.get("hold") == HOLD_CAPCUT_CREDIT_UNVERIFIED)
    narration = (REPO / ".cursor" / "skills" / "product-video-narration" / "SKILL.md").read_text(encoding="utf-8")
    check("credit-H-skill-allows-existing-consume", "Credits will be consumed" in narration and "approve_got_it" in narration)
    check(
        "credit-H-skill-blocks-new-contract",
        "Pro monthly/annual contract" in narration or "Pro 月額・年額契約" in narration,
    )


def test_chrome_mcp_docs() -> None:
    ref = (REPO / ".cursor" / "skills" / "product-video" / "references" / "capcut-chrome-mcp.md").read_text(
        encoding="utf-8"
    )
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    check("chrome-G-cdp-endpoint", "--cdp-endpoint=chrome" in ref and "--cdp-endpoint=chrome" in agents)
    check("chrome-G-no-ide-browser-fallback", "Do not fall back to `cursor-ide-browser`" in ref)
    check("chrome-G-mcp-json-not-git", "Do not add it to Git" in ref or "Do not add this file to Git" in ref)
    check("chrome-G-no-namespace-literal", "user-chatcut" not in ref and "project-0-" not in ref)
    check("chrome-G-hold-when-unavailable", "HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE" in ref)


def load_purge_helper():
    import importlib.util

    path = helper_path(REPO, "purge_local_working_media")
    spec = importlib.util.spec_from_file_location("purge_local_working_media", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_purge_preserves_shared_inputs() -> None:
    import argparse

    helper = load_purge_helper()
    check(
        "purge-owned-root-constant",
        helper.PERSISTENT_SHARED_INPUT_ROOTS == (PERSISTENT_SHARED_INPUT_RELATIVE,),
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"
        case_id = "pv-AN-S182-purge-test"
        task_root = root / "outputs" / case_id
        downloads = Path(directory) / "Downloads"
        nested = root / ".runtime" / "product-video-inputs" / "AN-S182_コピー" / "設置風景"
        for path in (
            root / "out",
            task_root / "tts",
            nested,
            downloads,
        ):
            path.mkdir(parents=True, exist_ok=True)
        helper.write_state(task_root, case_id, "COMPLETE", "drive", True)
        case_mp4 = task_root / "tts" / "c1.mp3"
        case_frame = task_root / "work.mp4"
        export_mp4 = root / "out" / f"{case_id}.mp4"
        library_mp4 = root / ".runtime" / "product-video-inputs" / "AN-S182_コピー" / "video.mp4"
        library_mov = nested / "video.mov"
        download_mp4 = downloads / f"{case_id}.mp4"
        case_mp4.write_bytes(b"tts-bytes")
        case_frame.write_bytes(b"case-video")
        export_mp4.write_bytes(b"export-bytes")
        library_mp4.write_bytes(b"library-mp4")
        library_mov.write_bytes(b"library-mov")
        download_mp4.write_bytes(b"download-bytes")
        dry = argparse.Namespace(
            project_root=root,
            task_root=task_root,
            case_id=case_id,
            execute=False,
            i_confirm_destination_stored=False,
            destination_stored_receipt=None,
            completed_video_filename=f"{case_id}.mp4",
            home_downloads_dir=downloads,
        )
        early = argparse.Namespace(**{**dry.__dict__, "execute": True, "i_confirm_destination_stored": True})
        helper.write_state(task_root, case_id, "ROUGH_EDIT", "drive", True)
        code, payload = helper.run_purge(early)
        check(
            "purge-E-before-verified-delivery",
            code == 2 and payload.get("hold") == helper.HOLD_NOT_DUE,
        )
        check("purge-E-keeps-case-media", case_mp4.exists() and library_mp4.exists())
        helper.write_state(task_root, case_id, "COMPLETE", "drive", True)

        code, payload = helper.run_purge(dry)
        planned_paths = {entry["path"] for entry in payload.get("planned") or []}
        check("purge-A-plans-task-tts", f"outputs/{case_id}/tts/c1.mp3" in planned_paths)
        check("purge-A-plans-task-video", f"outputs/{case_id}/work.mp4" in planned_paths)
        check("purge-F-no-library-in-dry-run", planned_hits_persistent_shared_inputs(payload.get("planned") or []) == [])
        check("purge-B-root-mp4-not-planned", not any(path.endswith("video.mp4") and is_persistent_shared_input_path(path) for path in planned_paths))
        check("purge-C-nested-mov-not-planned", not any(path.endswith("video.mov") and is_persistent_shared_input_path(path) for path in planned_paths))
        skipped_reasons = {item.get("reason") for item in payload.get("skipped") or []}
        check("purge-skip-reason-owned", PERSISTENT_SKIP_REASON in skipped_reasons)

        execute = argparse.Namespace(**{**dry.__dict__, "execute": True, "i_confirm_destination_stored": True})
        code, payload = helper.run_purge(execute)
        check("purge-A-execute-ok", code == 0)
        check("purge-A-deletes-task-media", not case_mp4.exists() and not case_frame.exists())
        check("purge-B-keeps-library-mp4", library_mp4.exists())
        check("purge-C-keeps-nested-mov", library_mov.exists())
        check("purge-D-zero-in-progress-still-keeps-library", library_mp4.exists() and library_mov.exists())


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
    test_material_video_preflight()
    test_capcut_credit_policy()
    test_chrome_mcp_docs()
    test_purge_preserves_shared_inputs()
    scratch = SCRIPTS / "_scratch"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    try:
        root = fake_project(scratch)
        test_speed_and_tts(root)
        test_tts_input_recovery(root)
        test_tts_runtime_gaps(root)
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
