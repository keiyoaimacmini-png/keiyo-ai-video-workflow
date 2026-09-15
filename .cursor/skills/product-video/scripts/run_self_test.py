#!/usr/bin/env python3
"""Local tests for /product-video. No live production, Gemini, CapCut, or Drive."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPTS))

from assembly import (  # noqa: E402
    adjacent_visual_diff,
    apply_minimal_range_padding,
    as_full_clip,
    assemble_plan,
    duration_passes,
    looks_similar,
    select_cut,
)
from approved_shots import load_history, record_shots  # noqa: E402
from caption_wrap import unwrap_visual, wrap_caption  # noqa: E402
from edit_plan import build_edit_plan, chatcut_execution_steps  # noqa: E402
from material_index import (  # noqa: E402
    alias_search_aid,
    candidates_from_index,
    expand_entry,
    load_aliases,
    meaning_match,
    refresh_index,
    save_aliases,
)
from visual_catalog import (  # noqa: E402
    apply_observed_scenes,
    load_catalog,
    refresh_catalog,
    scene_match_score,
    sidecar_describes_scene,
)
from narration_queue import finish_queue, record_queue_clip, start_queue  # noqa: E402
from timing import (  # noqa: E402
    ROUGH_EDIT_METRIC_KEYS,
    load_timing,
    mark_stage_end,
    mark_stage_start,
    record_rough_edit_metrics,
    summarize,
)
from bind_script_selection import bind_script_selection  # noqa: E402
from classify_capcut_credit import classify_capcut_credit  # noqa: E402
from constants import (  # noqa: E402
    DELIVERY_APPROVAL,
    DRIVE_DELIVERY_WARNING,
    HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
    HOLD_CAPCUT_CREDIT_UNVERIFIED,
    HOLD_CAPCUT_NEW_PURCHASE_REQUIRED,
    HOLD_INPUT_MATERIALS_REQUIRED,
    HOLD_MATERIAL_VIDEO_REQUIRED,
    HOLD_PREFLIGHT_REQUIRED,
    HOLD_PRODUCT_FACTS_REQUIRED,
    HOLD_SCRIPT_PRODUCT_GROUNDING,
    NARRATION_SPEED,
    OLD_SKILL_MARKERS,
    OPERATOR_ROUGH_MESSAGE,
    PERSISTENT_SHARED_INPUT_RELATIVE,
    PERSISTENT_SHARED_INPUT_ROOTS,
    operator_rough_message,
)
from delivery import may_complete, may_purge, may_start_job, prove_drive_ready, record_final_approved_shots  # noqa: E402
from dispatch import dispatch  # noqa: E402
from narration import gate_tts_generate, narration_speed, prepare_tts_input, record_clip, write_manifest  # noqa: E402
from prove_tts_speed import planned_editorial_duration, prove_editorial_timing, prove_tts_speed  # noqa: E402
from rough_edit import build_rough_edit, execute_from_edit_plan, prove_placed_narration_clip  # noqa: E402
from resolve_tts_text import compare_effective_to_frozen, resolve_effective_tts_text  # noqa: E402
from semantic_material_match import collect_scene_payloads, make_scene_id, parse_semantic_matches  # noqa: E402
from tts_attempts import generation_count_for_cut, load_attempts, may_generate_cut, record_generation_attempt  # noqa: E402
from tts_session import may_reuse_session, prove_session_setup, record_session_setup  # noqa: E402
from parse_gemini_scripts import parse_gemini_scripts  # noqa: E402
from paths import git_tracks, helper_path, helper_relpath, missing_git_tracked_helpers  # noqa: E402
from prepare import build_product_inputs, create_new_case, finish_prepare  # noqa: E402
from product_facts import (  # noqa: E402
    facts_path_for,
    load_product_facts_profile,
    prove_usable_product_facts,
    usable_product_facts,
)
from preserve_shared_inputs import (  # noqa: E402
    PERSISTENT_SKIP_REASON,
    is_persistent_shared_input_path,
    planned_hits_persistent_shared_inputs,
)
from prove_material_videos import prove_material_videos  # noqa: E402
from run_preflight import item, merge_preflight, retry_call, run_preflight  # noqa: E402
from prepare_tts_field import compare_tts_readback, diagnose_mismatch, is_pre_write_empty  # noqa: E402
from render_script_prompt import load_template, render_script_prompt  # noqa: E402
from script_fidelity import assert_immutable, freeze_approved_script  # noqa: E402
from script_grounding import (  # noqa: E402
    actual_facts_for_line,
    build_fact_catalog,
    line_matches_fact,
    present_for_operator,
    prove_scripts_grounding,
    prove_variant_grounding,
)
from script_stage import accept_gemini_output  # noqa: E402
from workflow_state import (  # noqa: E402
    clear_hold,
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


def grounded_sample_scripts(count: int) -> str:
    titles = ["熱中症型", "時短型", "共感型", "使用シーン型", "比較型"]
    body = ""
    for index in range(1, count + 1):
        body += (
            f"【案{index}：{titles[index - 1]}】\n"
            "想定完成尺：約45秒\n"
            "※ナレーション1.2倍速での想定\n"
            "カット1\n"
            "根拠ID：HOOK\n"
            "シチュエーション：\n"
            "「車内でハンドルを握る人物」\n"
            "セリフ：\n"
            "「車、サウナすぎん？」\n"
            "カット2\n"
            "根拠ID：F1\n"
            "シチュエーション：\n"
            "「サンシェードを広げる手元」\n"
            "セリフ：\n"
            "「日差しをサンシェードで遮る」\n"
            "カット3\n"
            "根拠ID：F2\n"
            "シチュエーション：\n"
            "「傘型サンシェードを開く手元」\n"
            "セリフ：\n"
            "「傘型でパッと開く」\n"
            "カット4\n"
            "根拠ID：F4\n"
            "シチュエーション：\n"
            "「サンシェードを装着する手元」\n"
            "セリフ：\n"
            "「装着が簡単すぎる」\n"
            "カット5\n"
            "根拠ID：CTA\n"
            "シチュエーション：\n"
            "「画面下のリンクを指す」\n"
            "セリフ：\n"
            "「下からチェック！」\n"
        )
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
    shutil.copy(
        REPO / ".cursor" / "skills" / "product-video" / "scripts" / "run_preflight.py",
        owned_scripts / "run_preflight.py",
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
    facts_profile = {
        "schema_version": "1",
        "product_model": "AN-S999",
        "verified_facts": ["車内の日差しを遮るサンシェード", "傘型でパッと開く"],
        "appeal_points": ["装着が簡単", "使わないときは畳んで収納できる"],
    }
    (config / "product_video_product_facts_AN-S999.v1.json").write_text(
        json.dumps(facts_profile, ensure_ascii=False) + "\n",
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
        "source_duration_seconds": 10.0,
        "visual": visual("person", "wide", "car"),
    }
    varied = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": "サンシェードを広げる手元",
        "scenario_tags": ["サンシェードを広げる手元"],
        "material_id": "varied",
        "source_duration_seconds": 10.0,
        "visual": visual("hands", "close", "dash"),
    }
    invalid = {
        "semantic_valid": False,
        "supported_line": line,
        "situation": "無関係な風景",
        "material_id": "invalid",
        "source_duration_seconds": 10.0,
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
        "source_duration_seconds": 10.0,
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


def test_adjacent_visual_variety() -> None:
    line = "設置したサンシェードで車内が涼しくなる"
    sit = "設置済みサンシェードの車内"
    cabin_installed = {
        "framing": "正面",
        "camera_distance": "正面",
        "location": "車内",
        "subject": "設置済みサンシェード",
        "action": "設置済み",
        "product_state": "設置済み",
        "objects": ["サンシェード", "ミラー"],
    }
    prev = {
        "source": "A.mov",
        "classification_folder": "車内涼しい",
        "visual": {key: cabin_installed[key] for key in ("framing", "camera_distance", "location", "subject", "action", "product_state")},
        "catalog_scene": {
            "objects": cabin_installed["objects"],
            "actions": ["設置済み"],
            "location": "車内",
            "product_state": "設置済み",
            "framing": "正面",
        },
    }
    same_look = {
        "semantic_valid": True,
        "from_visual_catalog": True,
        "visual_match": True,
        "visual_match_score": 4,
        "supported_line": line,
        "source": "B.mov",
        "material_id": "same-look-b",
        "source_duration_seconds": 10.0,
        "classification_folder": "車内涼しい",
        "visual": dict(prev["visual"]),
        "catalog_scene": dict(prev["catalog_scene"]),
        "source_in": 0.0,
        "source_out": 5.0,
    }
    different_look = {
        "semantic_valid": True,
        "from_visual_catalog": True,
        "visual_match": True,
        "visual_match_score": 2,
        "supported_line": line,
        "source": "C.mov",
        "material_id": "different-look",
        "source_duration_seconds": 10.0,
        "classification_folder": "車内涼しい",
        "visual": {
            "framing": "寄り",
            "camera_distance": "close",
            "location": "車内",
            "subject": "ハンドル",
            "action": "日陰",
            "product_state": "設置済み",
        },
        "catalog_scene": {
            "objects": ["ハンドル"],
            "actions": ["日陰"],
            "location": "車内",
            "product_state": "設置済み",
            "framing": "close",
        },
        "source_in": 0.0,
        "source_out": 5.0,
    }
    wrong_meaning = {
        "semantic_valid": False,
        "search_aid": True,
        "supported_line": line,
        "source": "D.mov",
        "material_id": "wrong-pack",
        "source_duration_seconds": 10.0,
        "classification_folder": "コンパクト収納",
        "visual": visual("hands", "close", "dash"),
        "source_in": 0.0,
        "source_out": 5.0,
    }
    check("variety-b-other-source-still-similar", looks_similar(prev, same_look) is True)
    check("variety-b-close-handle-not-similar", looks_similar(prev, different_look) is False)
    check("variety-b-diff-score-higher", adjacent_visual_diff(different_look, prev) > adjacent_visual_diff(same_look, prev))
    chosen = select_cut(
        [same_look, different_look],
        line=line,
        intended_scenario=sit,
        duration_seconds=2.5,
        previous=prev,
    )
    check("variety-a-prefers-visual-diff-over-catalog-score", chosen.get("selection", {}).get("material_id") == "different-look")
    unsafe = select_cut(
        [same_look, wrong_meaning],
        line=line,
        intended_scenario=sit,
        duration_seconds=2.5,
        previous=prev,
    )
    check("variety-c-never-wrong-meaning", unsafe.get("selection", {}).get("material_id") == "same-look-b")
    only = select_cut(
        [same_look],
        line=line,
        intended_scenario=sit,
        duration_seconds=2.5,
        previous=prev,
    )
    check("variety-d-one-candidate-ok", only.get("status") == "OK" and only.get("selection", {}).get("material_id") == "same-look-b")
    empty_prev = {
        "source": "IMG_3996.MOV",
        "classification_folder": "車内涼しい",
        "visual": {},
        "search_aid": True,
    }
    empty_other = {
        "semantic_valid": False,
        "search_aid": True,
        "supported_line": line,
        "source": "IMG_3997.MOV",
        "material_id": "empty-other",
        "source_duration_seconds": 10.0,
        "classification_folder": "車内涼しい",
        "visual": {},
        "source_in": 0.0,
        "source_out": 5.0,
    }
    check("variety-b-empty-same-folder-similar", looks_similar(empty_prev, empty_other) is True)
    tagged_same_folder = {
        "semantic_valid": False,
        "search_aid": True,
        "from_visual_catalog": True,
        "visual_match": False,
        "supported_line": line,
        "source": "IMG_3954.MOV",
        "material_id": "tagged-cool",
        "source_duration_seconds": 10.0,
        "classification_folder": "車内涼しい",
        "visual": {
            "framing": "",
            "camera_distance": "",
            "location": "",
            "subject": "車内涼しい 車内が陰になって快適に過ごせている様子",
            "action": "車内が陰になって快適に過ごせている様子",
        },
        "source_in": 0.0,
        "source_out": 5.0,
    }
    check("variety-b-tag-soup-same-folder-similar", looks_similar(empty_prev, tagged_same_folder) is True)
    tagged_plan = assemble_plan(
        {
            "cuts": [
                {"cut_id": "c1", "line": line, "situation": sit},
                {"cut_id": "c2", "line": line, "situation": sit},
            ]
        },
        {
            "clips": [
                {
                    "cut_id": "c1",
                    "line": line,
                    "audio_path": "a.mp3",
                    "source_duration_seconds": 3.0,
                    "editor_playback_rate": 1.2,
                    "planned_duration_seconds": 2.5,
                    "source_already_accelerated": False,
                },
                {
                    "cut_id": "c2",
                    "line": line,
                    "audio_path": "b.mp3",
                    "source_duration_seconds": 3.0,
                    "editor_playback_rate": 1.2,
                    "planned_duration_seconds": 2.5,
                    "source_already_accelerated": False,
                },
            ]
        },
        {"c1": [tagged_same_folder], "c2": [tagged_same_folder, empty_other]},
    )
    check(
        "variety-b-empty-folder-uses-unused-source",
        tagged_plan.get("status") == "OK" and (tagged_plan.get("cuts") or [{}, {}])[1].get("material_id") == "empty-other",
        str([(cut.get("material_id"), cut.get("source")) for cut in tagged_plan.get("cuts") or []]),
    )
    wide_prev2 = {
        "semantic_valid": True,
        "from_visual_catalog": True,
        "visual_match": True,
        "visual_match_score": 3,
        "source": "wide-a.mov",
        "material_id": "wide-install-a",
        "visual": {
            "framing": "wide",
            "camera_distance": "wide",
            "location": "parking_exterior",
            "subject": "サンシェード",
            "action": "設置",
            "product_state": "展開",
        },
        "catalog_scene": {
            "objects": ["サンシェード"],
            "actions": ["設置"],
            "location": "parking_exterior",
            "product_state": "展開",
            "framing": "wide",
        },
    }
    wide_prev = {
        "source": "wide-mid.mov",
        "visual": {
            "framing": "wide",
            "camera_distance": "wide",
            "location": "windshield_interior",
            "subject": "サンシェード",
            "action": "フィット",
            "product_state": "設置済み",
        },
        "catalog_scene": {
            "objects": ["サンシェード"],
            "actions": ["フィット"],
            "location": "windshield_interior",
            "product_state": "設置済み",
            "framing": "wide",
        },
    }
    wide_again = {
        "semantic_valid": True,
        "from_visual_catalog": True,
        "visual_match": True,
        "visual_match_score": 3,
        "supported_line": "傘のように開いて置くだけ",
        "source": "wide-b.mov",
        "material_id": "wide-install-b",
        "source_duration_seconds": 10.0,
        "visual": dict(wide_prev2["visual"]),
        "catalog_scene": dict(wide_prev2["catalog_scene"]),
        "source_in": 0.0,
        "source_out": 4.0,
    }
    close_vcut = {
        "semantic_valid": True,
        "from_visual_catalog": True,
        "visual_match": True,
        "visual_match_score": 3,
        "supported_line": "傘のように開いて置くだけ",
        "source": "close-v.mov",
        "material_id": "close-vcut",
        "source_duration_seconds": 10.0,
        "visual": {
            "framing": "close",
            "camera_distance": "close",
            "location": "windshield_interior",
            "subject": "ルームミラー",
            "action": "フィット",
            "product_state": "設置済み",
        },
        "catalog_scene": {
            "objects": ["ルームミラー"],
            "actions": ["フィット"],
            "location": "windshield_interior",
            "product_state": "設置済み",
            "framing": "close",
        },
        "source_in": 0.0,
        "source_out": 4.0,
    }
    third = select_cut(
        [wide_again, close_vcut],
        line="傘のように開いて置くだけ",
        intended_scenario="運転席から傘のように開く",
        duration_seconds=2.5,
        previous=wide_prev,
        previous_2=wide_prev2,
    )
    check("variety-e-avoids-prev2-same-axes", third.get("selection", {}).get("material_id") == "close-vcut")
    used_cabin = dict(same_look)
    used_cabin["source"] = "A.mov"
    used_cabin["material_id"] = "cabin-a"
    unused_similar = dict(same_look)
    unused_similar["source"] = "B.mov"
    unused_similar["material_id"] = "cabin-b"
    used_different = dict(different_look)
    used_different["source"] = "A.mov"
    used_different["material_id"] = "cabin-a-close"
    used_different["source_in"] = 6.0
    used_different["source_out"] = 10.0
    usage_plan = assemble_plan(
        {
            "cuts": [
                {"cut_id": "c1", "line": line, "situation": sit},
                {"cut_id": "c2", "line": line, "situation": sit},
            ]
        },
        {
            "clips": [
                {
                    "cut_id": "c1",
                    "line": line,
                    "audio_path": "a.mp3",
                    "source_duration_seconds": 3.0,
                    "editor_playback_rate": 1.2,
                    "planned_duration_seconds": 2.5,
                    "source_already_accelerated": False,
                },
                {
                    "cut_id": "c2",
                    "line": line,
                    "audio_path": "b.mp3",
                    "source_duration_seconds": 3.0,
                    "editor_playback_rate": 1.2,
                    "planned_duration_seconds": 2.5,
                    "source_already_accelerated": False,
                },
            ]
        },
        {
            "c1": [used_cabin],
            "c2": [unused_similar, used_different],
        },
    )
    check("variety-source-spread-does-not-beat-look", usage_plan.get("status") == "OK", str(usage_plan.get("hold")))
    check(
        "variety-c2-keeps-different-look",
        (usage_plan.get("cuts") or [{}, {}])[1].get("material_id") == "cabin-a-close",
        str([(cut.get("cut_id"), cut.get("material_id"), cut.get("source")) for cut in usage_plan.get("cuts") or []]),
    )
    equal_a = dict(different_look)
    equal_a["source"] = "E.mov"
    equal_a["material_id"] = "equal-a"
    equal_b = dict(different_look)
    equal_b["source"] = "F.mov"
    equal_b["material_id"] = "equal-b"
    spread = assemble_plan(
        {
            "cuts": [
                {"cut_id": "c1", "line": line, "situation": sit},
                {"cut_id": "c2", "line": line, "situation": sit},
            ]
        },
        {
            "clips": [
                {
                    "cut_id": "c1",
                    "line": line,
                    "audio_path": "a.mp3",
                    "source_duration_seconds": 3.0,
                    "editor_playback_rate": 1.2,
                    "planned_duration_seconds": 2.5,
                    "source_already_accelerated": False,
                },
                {
                    "cut_id": "c2",
                    "line": line,
                    "audio_path": "b.mp3",
                    "source_duration_seconds": 3.0,
                    "editor_playback_rate": 1.2,
                    "planned_duration_seconds": 2.5,
                    "source_already_accelerated": False,
                },
            ]
        },
        {"c1": [equal_a], "c2": [equal_a, equal_b]},
    )
    check("variety-f-spread-when-look-equal", spread.get("status") == "OK" and (spread.get("cuts") or [{}, {}])[1].get("material_id") == "equal-b")
    unmatched_catalog = {
        "semantic_valid": False,
        "from_visual_catalog": True,
        "visual_match": False,
        "visual_match_score": 0,
        "search_aid": True,
        "supported_line": "下からチェック！",
        "source": "pouch-unmatched.mov",
        "material_id": "unmatched-pouch",
        "source_duration_seconds": 10.0,
        "classification_folder": "コンパクト収納",
        "visual": visual("hands", "close", "dash"),
        "source_in": 0.0,
        "source_out": 5.0,
    }
    matched_cta = {
        "semantic_valid": True,
        "from_visual_catalog": True,
        "visual_match": True,
        "visual_match_score": 1,
        "supported_line": "下からチェック！",
        "source": "cta.mov",
        "material_id": "matched-cta",
        "source_duration_seconds": 10.0,
        "classification_folder": "ラストカット",
        "visual": visual("person", "wide", "park"),
        "source_in": 0.0,
        "source_out": 5.0,
    }
    meaning_first = select_cut(
        [unmatched_catalog, matched_cta],
        line="下からチェック！",
        intended_scenario="収納ポーチを下から指差す",
        duration_seconds=1.2,
        previous={
            "source": "pouch.mov",
            "classification_folder": "コンパクト収納",
            "visual": visual("hands", "close", "dash"),
        },
    )
    check("variety-c-catalog-unmatched-not-same-tier", meaning_first.get("selection", {}).get("material_id") == "matched-cta")


def test_assembly_duration_gate() -> None:
    line = "これ一枚で全然違う。"
    situation = "サンシェードを広げる手元"
    long_enough = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": situation,
        "scenario_tags": [situation],
        "material_id": "long",
        "source": "long.mov",
        "source_duration_seconds": 12.0,
        "visual": visual("hands", "close", "dash"),
    }
    scene_short = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": situation,
        "scenario_tags": [situation],
        "material_id": "scene-short",
        "source": "umbrella.mov",
        "source_in": 1.5,
        "source_out": 3.8,
        "source_duration_seconds": 12.0,
        "visual": visual("hands", "close", "dash"),
    }
    file_short = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": situation,
        "scenario_tags": [situation],
        "material_id": "file-short",
        "source": "tiny.mov",
        "source_duration_seconds": 2.0,
        "visual": visual("person", "wide", "car"),
    }
    excluded = select_cut(
        [scene_short, file_short],
        line=line,
        intended_scenario=situation,
        duration_seconds=3.0,
    )
    check("duration-excludes-short-scene-and-file", excluded.get("status") == "HOLD")
    check("duration-scene-range-not-file-length", duration_passes(scene_short, 3.0) is False)
    check("duration-full-clip-uses-file-length", duration_passes(long_enough, 3.0) is True)
    chosen = select_cut(
        [scene_short, long_enough],
        line=line,
        intended_scenario=situation,
        duration_seconds=3.0,
    )
    check("duration-ranks-only-passers", chosen.get("selection", {}).get("material_id") == "long")
    check("duration-stamps-target", chosen.get("selection", {}).get("target_duration_seconds") == 3.0)
    check("duration-stamps-available", chosen.get("selection", {}).get("available_duration") == 3.0)
    check("duration-stamps-source-range", chosen.get("selection", {}).get("source_in") == 0.0)
    weaker_history = {
        "schema": "product_video_approved_shot_history.v1",
        "shots": [
            {
                "source": ".runtime/product-video-inputs/AN-S999_コピー/old.mov",
                "in_sec": 0.0,
                "out_sec": 4.0,
                "line": line,
                "situation": "別アングルの車外",
                "semantic_tags": ["別アングルの車外"],
                "visual": visual("person", "wide", "park"),
            }
        ],
    }
    situation_first = select_cut(
        [long_enough],
        line=line,
        intended_scenario=situation,
        duration_seconds=3.0,
        history=weaker_history,
    )
    check(
        "situation-beats-weaker-history",
        situation_first.get("selection", {}).get("material_id") == "long"
        and situation_first.get("selection", {}).get("from_approved_history") is not True,
    )
    history = {
        "schema": "product_video_approved_shot_history.v1",
        "shots": [
            {
                "source": ".runtime/product-video-inputs/AN-S999_コピー/clip.mov",
                "in_sec": 3.5,
                "out_sec": 5.92,
                "line": line,
                "situation": situation,
                "semantic_tags": [situation],
                "visual": visual("hands", "close", "dash"),
            }
        ],
    }
    history_short = select_cut(
        [long_enough],
        line=line,
        intended_scenario=situation,
        duration_seconds=3.52,
        history=history,
    )
    check(
        "duration-rejects-short-history",
        history_short.get("selection", {}).get("from_approved_history") is not True
        and history_short.get("selection", {}).get("material_id") == "long",
    )
    expanded = as_full_clip(scene_short, 12.0, 3.0)
    check("full-clip-helper-fits-target", expanded is not None and expanded["available_duration"] >= 3.0)


def ready_tts_session_observation(**overrides: Any) -> dict[str, Any]:
    observation = {
        "chrome_mcp_attached": True,
        "capcut_tts_page_ready": True,
        "holiday_twist_selected": True,
        "tts_input_field_identified": True,
        "credit_policy_ready": True,
        "field_id": "capcut-tts-textarea",
    }
    observation.update(overrides)
    return observation


def test_tts_session(root: Path) -> None:
    case_id = "pv-AN-S999-tts-session"
    first = record_session_setup(root, case_id, ready_tts_session_observation())
    check("session-setup-once", first.get("setup") is True and first.get("reuse") is True)
    reused = may_reuse_session({"schema": "product_video_tts_session.v1", "setup": True, "recover_count": 0}, ready_tts_session_observation())
    check("session-reuse-skips-setup", reused.get("reuse") is True and reused.get("setup") is False)
    check("session-reuse-skips-mcp", reused.get("skip_mcp_rediscovery") is True)
    check("session-reuse-skips-page", reused.get("skip_page_research") is True)
    check("session-reuse-skips-voice", reused.get("skip_holiday_twist_reselect") is True)
    lost = prove_session_setup({"chrome_mcp_attached": False}, recover_count=0)
    check("session-lost-recovers", lost.get("recover") is True and lost.get("hold") is None)
    held = prove_session_setup({"chrome_mcp_attached": False}, recover_count=3)
    check("session-lost-existing-hold", held.get("hold") == HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE)
    login = prove_session_setup({"capcut_login_required": True}, recover_count=3)
    check("session-lost-login-existing-hold", login.get("hold") == "HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED")
    src = (REPO / ".cursor" / "skills" / "product-video" / "scripts" / "tts_session.py").read_text(encoding="utf-8")
    holds = set(re.findall(r"HOLD_[A-Z0-9_]+", src))
    check(
        "session-no-new-hold",
        holds <= {HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED"},
        str(holds),
    )
    skill = (REPO / ".cursor" / "skills" / "product-video-narration" / "SKILL.md").read_text(encoding="utf-8")
    check("session-skill-once", "Session setup (once)" in skill)
    check("session-skill-no-per-cut-chat", "Do not chat after a successful cut" in skill)
    check("session-skill-keep-page", "same Chrome tab" in skill or "same session" in skill)
    check("session-skill-queue", "narration_queue.py" in skill)
    check("session-skill-no-dispatch-mid-queue", "Do not return to `/product-video` dispatch" in skill)


def test_approved_shot_history(root: Path) -> None:
    line = "これ一枚で全然違う。"
    situation = "サンシェードを広げる手元"
    history_source = ".runtime/product-video-inputs/AN-S999_コピー/clip.mov"
    recorded = record_shots(
        root,
        "AN-S999",
        "pv-AN-S999-hist",
        [
            {
                "source": history_source,
                "in_sec": 1.0,
                "out_sec": 3.5,
                "line": line,
                "situation": situation,
                "semantic_tags": [situation],
                "visual": visual("hands", "close", "dash"),
            },
            {
                "source": "outputs/pv-AN-S999-hist/2026_0913_AN-S999_AI作成①.mp4",
                "line": line,
                "situation": situation,
            },
        ],
    )
    check("history-writes-source-only", recorded.get("status") == "OK" and recorded.get("shot_count") == 1)
    history = load_history(root, "AN-S999")
    check("history-skips-completed-export", history["shots"][0]["source"] == history_source)
    other = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": situation,
        "scenario_tags": [situation],
        "material_id": "fresh",
        "source": ".runtime/product-video-inputs/AN-S999_コピー/other.mov",
        "source_duration_seconds": 10.0,
        "visual": visual("hands", "wide", "dash"),
    }
    chosen = select_cut(
        [other],
        line=line,
        intended_scenario=situation,
        duration_seconds=2.5,
        history=history,
    )
    check("history-is-first-candidate", chosen.get("selection", {}).get("from_approved_history") is True)
    check("history-keeps-range", chosen.get("selection", {}).get("in_sec") == 1.0)
    fallback = select_cut([other], line=line, intended_scenario=situation, duration_seconds=2.5)
    check("no-history-uses-current", fallback.get("selection", {}).get("material_id") == "fresh")
    same = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": situation,
        "source": history_source,
        "material_id": "same",
        "source_duration_seconds": 10.0,
        "visual": visual("hands", "close", "dash"),
    }
    alt = {
        "semantic_valid": True,
        "supported_line": line,
        "situation": situation,
        "source": ".runtime/product-video-inputs/AN-S999_コピー/other.mov",
        "material_id": "varied",
        "source_duration_seconds": 10.0,
        "visual": visual("person", "wide", "car"),
    }
    previous = {"source": history_source, "visual": visual("hands", "close", "dash")}
    avoided = select_cut(
        [same, alt],
        line=line,
        intended_scenario=situation,
        duration_seconds=2.5,
        previous=previous,
    )
    check("consecutive-same-source-angle-avoided", avoided.get("selection", {}).get("material_id") == "varied")
    case_id = "pv-AN-S999-final"
    case = root / "outputs" / case_id
    receipts = case / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (case / "approved-script.json").write_text(
        json.dumps({"cuts": [{"cut_id": "c1", "line": line, "situation": situation}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (case / "assembly-plan.json").write_text(
        json.dumps(
            {
                "cuts": [
                    {
                        "cut_id": "c1",
                        "line": line,
                        "situation": situation,
                        "source": ".runtime/product-video-inputs/AN-S999_コピー/old.mov",
                        "in_sec": 0.0,
                        "out_sec": 2.0,
                        "scenario_tags": [situation],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (receipts / "picture_swap_c1.json").write_text(
        json.dumps(
            {
                "cuts": {
                    "c1": {
                        "source": ".runtime/product-video-inputs/AN-S999_コピー/swapped.mov",
                        "in_sec": 4.5,
                        "out_sec": 7.0,
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    swapped = record_final_approved_shots(root, {"case_id": case_id, "product_model": "AN-S999"})
    check("complete-records-swap", swapped.get("recorded") is True)
    stored = load_history(root, "AN-S999")
    check(
        "complete-uses-final-source",
        any(item.get("source", "").endswith("swapped.mov") and item.get("in_sec") == 4.5 for item in stored["shots"]),
    )
    check("complete-does-not-hold", swapped.get("hold") is None)


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
    warned = build_rough_edit(
        script,
        plan,
        manifest,
        editor_project_identity="chatcut:proj-1",
        placed_telops=[{"cut_id": "c1", "text": "下からチェック！"}],
        delivery_ready=False,
    )
    check(
        "operator-message-drive-warning",
        warned.get("operator_message_ja") == operator_rough_message(delivery_ready=False)
        and "Drive格納準備:" in (warned.get("operator_message_ja") or ""),
    )
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


def test_narration_queue(root: Path) -> None:
    case_id = "pv-AN-S999-queue"
    case = root / "outputs" / case_id
    case.mkdir(parents=True, exist_ok=True)
    script = {
        "schema": "product_video_approved_script.v1",
        "variant_id": 1,
        "title": "queue",
        "cuts": [
            {"cut_id": "c1", "index": 1, "line": "車、サウナすぎん？", "situation": "車内"},
            {"cut_id": "c2", "index": 2, "line": "これ一枚で全然違う。", "situation": "手元"},
        ],
    }
    (case / "approved-script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    first = start_queue(root, case_id)
    check("queue-starts-setup", first.get("setup_session") is True and first.get("cut_id") == "c1")
    check("queue-no-dispatch-before-done", first.get("return_to_dispatch") is False and first.get("skip_dispatch") is True)
    check("queue-no-chat", first.get("skip_chat") is True and first.get("skip_llm_plan") is True)
    check("queue-no-manifest-yet", first.get("write_manifest") is False)
    recorded = record_queue_clip(
        root,
        case_id,
        cut_id="c1",
        line="車、サウナすぎん？",
        audio_path="c1.mp3",
        source_duration_seconds=2.4,
    )
    check("queue-next-cut-no-setup", recorded.get("cut_id") == "c2" and recorded.get("setup_session") is not True)
    check("queue-skips-mcp-between-cuts", recorded.get("skip_mcp_rediscovery") is True)
    check("queue-skips-voice-between-cuts", recorded.get("skip_voice_reselect") is True)
    check("queue-skips-page-between-cuts", recorded.get("skip_page_research") is True)
    check("queue-still-no-manifest", recorded.get("write_manifest") is False and recorded.get("return_to_dispatch") is False)
    early_finish = finish_queue(root, case_id)
    check("queue-finish-blocked-until-all", early_finish.get("queue_complete") is False)
    check("queue-no-manifest-file-yet", not (case / "narration-manifest.json").is_file())
    record_queue_clip(
        root,
        case_id,
        cut_id="c2",
        line="これ一枚で全然違う。",
        audio_path="c2.mp3",
        source_duration_seconds=3.0,
    )
    done = finish_queue(root, case_id)
    check("queue-writes-manifest-once", done.get("write_manifest") is True and done.get("clip_count") == 2)
    check("queue-returns-to-dispatch-after-all", done.get("return_to_dispatch") is True)
    manifest = json.loads((case / "narration-manifest.json").read_text(encoding="utf-8"))
    check("queue-manifest-has-both-cuts", [clip["cut_id"] for clip in manifest.get("clips") or []] == ["c1", "c2"])


def test_material_index_and_edit_plan(root: Path) -> None:
    product = "AN-S997"
    materials = root / ".runtime" / "product-video-inputs" / f"{product}_コピー" / "手元"
    materials.mkdir(parents=True)
    video = materials / "clip.mov"
    video.write_bytes(b"video-bytes")
    (materials / "clip.md").write_text(
        "duration: 12.0\nsituation: サンシェードを広げる手元\ntags: 手元, 展開\nframing: close\nsource_in: 1.0\nsource_out: 5.0\n",
        encoding="utf-8",
    )
    probes: list[str] = []

    def probe(path: Path) -> float:
        probes.append(path.name)
        return 12.0

    first = refresh_index(root, product, materials.parent, probe_fn=probe)
    check("index-refresh-once", first.get("status") == "OK" and int(first.get("file_count") or 0) == 1)
    second = refresh_index(root, product, materials.parent, probe_fn=probe)
    check("index-skips-unchanged", second.get("reused") == 1 and second.get("refreshed") == 0)
    check("index-does-not-reprobe", probes == [])
    mixed = expand_entry(
        {
            "source": "empty.mov",
            "situation": "",
            "semantic_tags": [],
            "full_duration": 10.0,
        },
        line="骨組みは頼れる10本骨構造！",
        situation="裏面の10本骨が見える寄り",
    )
    check("index-does-not-copy-requested-situation", mixed[0]["situation"] == "")
    check("index-keeps-intended-scenario", mixed[0]["intended_scenario"] == "裏面の10本骨が見える寄り")
    case_id = "pv-AN-S997-plan"
    case = root / "outputs" / case_id
    case.mkdir(parents=True)
    line = "これ一枚で全然違う。"
    situation = "サンシェードを広げる手元"
    script = {
        "schema": "product_video_approved_script.v1",
        "cuts": [{"cut_id": "c1", "index": 1, "line": line, "situation": situation}],
    }
    manifest = {
        "clips": [
            {
                "cut_id": "c1",
                "line": line,
                "audio_path": "c1.mp3",
                "source_duration_seconds": 3.6,
                "editor_playback_rate": 1.2,
                "planned_duration_seconds": 3.0,
                "source_already_accelerated": False,
            }
        ]
    }
    assembly = assemble_plan(
        script,
        manifest,
        {
            "c1": [
                {
                    "semantic_valid": True,
                    "supported_line": line,
                    "situation": situation,
                    "scenario_tags": [situation],
                    "material_id": "clip",
                    "source": ".runtime/product-video-inputs/AN-S997_コピー/手元/clip.mov",
                    "source_in": 1.0,
                    "source_out": 5.0,
                    "source_duration_seconds": 12.0,
                    "visual": visual("hands", "close", "dash"),
                }
            ]
        },
    )
    planned = build_edit_plan(script, assembly, manifest)
    check("edit-plan-ok", planned.get("status") == "OK", str(planned.get("hold")))
    cut = (planned.get("cuts") or [{}])[0]
    check("edit-plan-has-timeline", cut.get("timeline_start_frame") == 0 and cut.get("timeline_end_frame") == 90)
    check("edit-plan-has-wrap", unwrap_visual(cut.get("caption_visual_wrap") or "") == line)
    check("edit-plan-exact-caption", cut.get("caption_text") == line)
    check("edit-plan-no-reselect", planned.get("reselect_in_editor") is False)
    check("edit-plan-has-import-batches", bool(planned.get("chatcut_steps")))
    ops = [step.get("op") for step in planned.get("chatcut_steps") or [] if isinstance(step, dict)]
    check("edit-plan-one-place-audio", ops.count("place_audio") == 1)
    check("edit-plan-one-playback-rate", ops.count("set_playback_rate") == 1)
    check("edit-plan-one-place-video", ops.count("place_video") == 1)
    check("edit-plan-one-place-captions", ops.count("place_captions") == 1)
    check("edit-plan-final-verify-last", ops[-1] == "final_verify")
    audio_step = next(step for step in planned.get("chatcut_steps") or [] if step.get("op") == "place_audio")
    check("edit-plan-audio-adds-batched", isinstance(audio_step.get("adds"), list) and len(audio_step.get("adds") or []) == 1)
    executed = execute_from_edit_plan(planned, editor_project_identity="chatcut:proj-speed")
    check("rough-executes-plan", executed.get("usable_rough_edit") is True and executed.get("reselect_in_editor") is False)
    batched = chatcut_execution_steps(
        {
            "cuts": [
                {
                    "cut_id": "c1",
                    "narration_audio_path": "a1.mp3",
                    "video_source": "v1.mov",
                    "timeline_start_frame": 0,
                    "duration_frames": 10,
                    "source_in": 0.0,
                    "caption_text": "一行目です。",
                    "caption_visual_wrap": "一行目です。",
                },
                {
                    "cut_id": "c2",
                    "narration_audio_path": "a2.mp3",
                    "video_source": "v2.mov",
                    "timeline_start_frame": 10,
                    "duration_frames": 12,
                    "source_in": 1.0,
                    "caption_text": "二行目です。",
                    "caption_visual_wrap": "二行目です。",
                },
            ]
        }
    )
    audio_adds = next(step["adds"] for step in batched if step.get("op") == "place_audio")
    rate_updates = next(step["updates"] for step in batched if step.get("op") == "set_playback_rate")
    video_adds = next(step["adds"] for step in batched if step.get("op") == "place_video")
    cards = next(step["cards"] for step in batched if step.get("op") == "place_captions")
    check("edit-plan-audio-two-cuts-one-call", len(audio_adds) == 2)
    check("edit-plan-rate-two-cuts-one-call", len(rate_updates) == 2)
    check("edit-plan-video-two-cuts-one-call", len(video_adds) == 2)
    check("edit-plan-captions-two-cuts-one-call", len(cards) == 2)


def test_semantic_folder_aliases(root: Path) -> None:
    product = "AN-S996"
    aliases = {
        "他社製品比較": ["吸盤", "蛇腹", "落ちる", "外れる", "ズレる", "他社", "比較"],
        "設置風景": ["設置", "フロントガラス", "V字", "V字カット", "ミラー", "ルームミラー", "フィット", "合わせる"],
        "車内涼しい": ["日差し", "直射日光", "紫外線", "UV", "UPF", "遮る", "ブロック", "陰"],
        "コンパクト収納": ["閉じる", "畳む", "たたむ", "収納", "ポーチ", "スリム", "コンパクト"],
    }
    save_aliases(root, {"product_model": product, "folder_aliases": aliases})
    loaded = load_aliases(root, product)
    check("aliases-persist-product-level", loaded.get("他社製品比較") == aliases["他社製品比較"])

    competitor = {
        "classification_folder": "他社製品比較",
        "situation": "",
        "semantic_tags": ["他社製品比較"],
        "source": "competitor.mov",
        "full_duration": 10.0,
    }
    install = {
        "classification_folder": "設置風景",
        "situation": "",
        "semantic_tags": ["設置風景"],
        "source": "install.mov",
        "full_duration": 10.0,
    }
    cool = {
        "classification_folder": "車内涼しい",
        "situation": "",
        "semantic_tags": ["車内涼しい"],
        "source": "cool.mov",
        "full_duration": 8.0,
    }
    packed = {
        "classification_folder": "コンパクト収納",
        "situation": "",
        "semantic_tags": ["コンパクト収納"],
        "source": "pack.mov",
        "full_duration": 9.0,
    }
    exact = {
        "classification_folder": "設置風景",
        "situation": "専用の完全一致シチュエーション",
        "semantic_tags": ["設置風景"],
        "source": "exact.mov",
        "full_duration": 11.0,
    }

    def folders_for(line: str, situation: str) -> set[str]:
        index = {"files": {"a": competitor, "b": install, "c": cool, "d": packed, "e": exact}}
        matched = [
            item["classification_folder"]
            for item in candidates_from_index(index, line=line, situation=situation, folder_aliases=loaded)
            if item.get("semantic_valid") is True
        ]
        return set(matched)

    def search_aid_folders(line: str, situation: str) -> set[str]:
        index = {"files": {"a": competitor, "b": install, "c": cool, "d": packed, "e": exact}}
        matched = [
            item["classification_folder"]
            for item in candidates_from_index(index, line=line, situation=situation, folder_aliases=loaded)
            if item.get("search_aid") is True
        ]
        return set(matched)

    check(
        "alias-sucker-search-aid-competitor",
        search_aid_folders("吸盤がすぐ落ちるサンシェード、もう限界…", "蛇腹式の吸盤サンシェードがペラッと落ちてきてイラッとする人物")
        == {"他社製品比較"},
    )
    check(
        "alias-sucker-not-semantic-valid",
        folders_for("吸盤がすぐ落ちるサンシェード、もう限界…", "蛇腹式の吸盤サンシェードがペラッと落ちてきてイラッとする人物")
        == set(),
    )
    check(
        "alias-vcut-search-aid-install",
        search_aid_folders("こだわりのV字カット加工で…", "V字カットがルームミラーの支柱をきれいに逃がしている様子")
        == {"設置風景"},
    )
    check(
        "alias-vcut-not-semantic-valid",
        folders_for("こだわりのV字カット加工で…", "V字カットがルームミラーの支柱をきれいに逃がしている様子")
        == set(),
    )
    check(
        "alias-uv-search-aid-cool",
        search_aid_folders("UV約99パーセントカット＆UPF40以上！", "車内が陰になって快適に過ごせている様子")
        == {"車内涼しい"},
    )
    check(
        "generic-sunshine-not-search-aid",
        alias_search_aid(cool, "日差しが強い日", "", folder_aliases=loaded) is False,
    )
    check(
        "generic-install-word-not-search-aid",
        alias_search_aid(install, "毎日の設置が簡単", "", folder_aliases=loaded) is False,
    )
    check(
        "alias-close-to-storage-search-aid",
        search_aid_folders("使い終わったらシュッと閉じて…", "傘をシュッと閉じてコンパクトにまとめる一連の動作")
        >= {"コンパクト収納"},
    )
    check(
        "alias-close-word-is-search-aid",
        alias_search_aid(packed, "使い終わったら閉じる", "", folder_aliases=loaded) is True
        and meaning_match(packed, "使い終わったら閉じる", "", folder_aliases=loaded) is False,
    )
    check(
        "alias-storage-word-is-search-aid",
        alias_search_aid(packed, "付属ポーチへ収納", "", folder_aliases=loaded) is True
        and meaning_match(packed, "付属ポーチへ収納", "", folder_aliases=loaded) is False,
    )
    check(
        "alias-unrelated-does-not-match",
        folders_for("りんごを切る", "台所のテーブル") == set()
        and search_aid_folders("りんごを切る", "台所のテーブル") == set(),
    )
    check(
        "alias-sidecar-exact-still-used",
        meaning_match(exact, "別のセリフでもよい", "専用の完全一致シチュエーション", folder_aliases=loaded) is True,
    )

    short = {
        "semantic_valid": True,
        "supported_line": None,
        "situation": "吸盤が落ちる従来品",
        "classification_folder": "他社製品比較",
        "material_id": "short",
        "source": "short.mov",
        "source_duration_seconds": 1.2,
        "visual": visual("hands", "close", "dash"),
    }
    long_enough = {
        "semantic_valid": True,
        "supported_line": None,
        "situation": "吸盤が落ちる従来品",
        "classification_folder": "他社製品比較",
        "material_id": "long",
        "source": "long.mov",
        "source_duration_seconds": 10.0,
        "visual": visual("hands", "wide", "car"),
    }
    duration_hold = select_cut(
        [short],
        line="吸盤が落ちる",
        intended_scenario="従来品が落ちる",
        duration_seconds=3.0,
    )
    check("alias-short-still-excluded", duration_hold.get("status") == "HOLD")
    chosen = select_cut(
        [short, long_enough],
        line="吸盤が落ちる",
        intended_scenario="従来品が落ちる",
        duration_seconds=3.0,
    )
    check("alias-duration-keeps-long", chosen.get("selection", {}).get("material_id") == "long")


def test_visual_catalog_onboarding(root: Path) -> None:
    product = "AN-S995"
    material_root = root / ".runtime" / "product-video-inputs" / f"{product}_コピー"
    sidecar_dir = material_root / "手元"
    folder_only = material_root / "設置風景"
    sidecar_dir.mkdir(parents=True)
    folder_only.mkdir(parents=True)
    rich = sidecar_dir / "clip.mov"
    poor = folder_only / "IMG_0369.MOV"
    rich.write_bytes(b"video-bytes")
    poor.write_bytes(b"folder-only")
    (sidecar_dir / "clip.md").write_text(
        "duration: 12.0\nsituation: サンシェードを広げる手元\ntags: 手元, 展開\nframing: close\nsource_in: 1.0\nsource_out: 5.0\n",
        encoding="utf-8",
    )
    check(
        "catalog-sidecar-is-sufficient",
        sidecar_describes_scene(
            {
                "situation": "サンシェードを広げる手元",
                "source_in": 1.0,
                "source_out": 5.0,
                "semantic_tags": ["手元"],
            }
        )
        is True,
    )
    check(
        "catalog-folder-only-is-insufficient",
        sidecar_describes_scene({"situation": "", "semantic_tags": ["設置風景"]}) is False,
    )
    first = refresh_catalog(root, product, material_root)
    check("catalog-refresh-ok", first.get("status") == "OK" and int(first.get("file_count") or 0) == 2)
    catalog = load_catalog(root, product)
    rich_entry = next(item for item in catalog["files"].values() if str(item.get("source") or "").endswith("clip.mov"))
    poor_entry = next(item for item in catalog["files"].values() if "IMG_0369" in str(item.get("source") or ""))
    check("catalog-ingests-sidecar-without-watch", rich_entry.get("needs_observation") is False and rich_entry.get("scenes"))
    check("catalog-does-not-confirm-folder-name", poor_entry.get("needs_observation") is True and not poor_entry.get("scenes"))
    check(
        "catalog-folder-not-used-as-description",
        all("設置風景" != str(scene.get("factual_description") or "") for scene in (poor_entry.get("scenes") or [])),
    )
    second = refresh_catalog(root, product, material_root)
    check("catalog-skips-unchanged", second.get("reused") == 2 and second.get("refreshed") == 0)
    apply_observed_scenes(
        catalog,
        [
            {
                "source": poor_entry["source"],
                "source_in": 2.8,
                "source_out": 6.4,
                "objects": ["サンシェード", "ルームミラー", "フロントガラス"],
                "actions": ["設置済み"],
                "visible_features": ["V字カット"],
                "factual_description": "設置済みのサンシェードのV字部分がルームミラー支柱を避けている",
            }
        ],
    )
    from visual_catalog import save_catalog

    save_catalog(root, catalog)
    third = refresh_catalog(root, product, material_root)
    check("catalog-keeps-observation-on-unchanged", third.get("reused") == 2)
    stored = load_catalog(root, product)
    observed = next(item for item in stored["files"].values() if "IMG_0369" in str(item.get("source") or ""))
    check("catalog-observation-has-vcut", any("V字カット" in (scene.get("visible_features") or []) for scene in observed.get("scenes") or []))


def _catalog_candidate(
    source: str,
    *,
    source_in: float,
    source_out: float,
    objects: list[str],
    actions: list[str] | None = None,
    features: list[str] | None = None,
    description: str,
    duration: float = 12.0,
    search_aid: bool = False,
) -> dict[str, Any]:
    scene = {
        "source": source,
        "source_in": source_in,
        "source_out": source_out,
        "duration": source_out - source_in,
        "objects": objects,
        "actions": actions or [],
        "product_state": "",
        "location": "",
        "visible_features": features or [],
        "framing": "",
        "factual_description": description,
    }
    return {
        "semantic_valid": False,
        "search_aid": search_aid,
        "supported_line": None,
        "situation": description,
        "intended_scenario": "",
        "source": source,
        "material_id": source,
        "source_in": source_in,
        "source_out": source_out,
        "source_duration_seconds": duration,
        "available_duration": source_out - source_in,
        "catalog_scene": scene,
        "from_visual_catalog": True,
        "alternate_ranges": [(source_in, source_out)],
        "visual": visual("product", "close", "cabin"),
    }


def test_selection_quality_case_cuts() -> None:
    hot = {
        "semantic_valid": False,
        "search_aid": True,
        "supported_line": None,
        "situation": "",
        "source": ".runtime/product-video-inputs/AN-S182_コピー/車内暑い/IMG_3898.MOV",
        "material_id": "hot-cabin",
        "source_duration_seconds": 10.0,
        "classification_folder": "車内暑い",
        "visual": visual("person", "wide", "car"),
    }
    ribs = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_3963.mov",
        source_in=0.6,
        source_out=3.16,
        objects=["骨組み", "10本骨"],
        features=["10本骨"],
        description="裏面の頑丈な10本の骨組みが見える",
    )
    ribs["material_id"] = "ribs"
    vcut = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_3893.MOV",
        source_in=0.05,
        source_out=2.17,
        objects=["サンシェード", "ルームミラー"],
        features=["V字カット"],
        description="設置済みのサンシェードのV字部分がルームミラー支柱を避けている",
    )
    vcut["material_id"] = "vcut"
    pouch = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/コンパクト収納/IMG_3869.MOV",
        source_in=1.5,
        source_out=4.52,
        objects=["ポーチ"],
        actions=["閉じる", "畳む"],
        features=["収納"],
        description="本体を収納ポーチへ滑り込ませる",
    )
    pouch["material_id"] = "pouch"
    uv = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/車内涼しい/shade.mov",
        source_in=1.0,
        source_out=5.0,
        objects=["サンシェード"],
        features=["UVカット", "日陰"],
        description="サンシェードで車内が陰になっている",
    )
    uv["material_id"] = "uv-shade"
    install_a = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_0369.MOV",
        source_in=2.8,
        source_out=6.4,
        objects=["サンシェード", "ルームミラー", "フロントガラス"],
        actions=["設置済み"],
        features=["V字カット"],
        description="設置済みのサンシェードのV字部分がルームミラー支柱を避けている",
        search_aid=True,
    )
    install_a["material_id"] = "img0369-vcut"
    install_b = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_0369.MOV",
        source_in=8.0,
        source_out=12.0,
        objects=["サンシェード"],
        actions=["広げる"],
        description="サンシェードをフロントガラスへ広げている",
        search_aid=True,
    )
    install_b["material_id"] = "img0369-spread"
    zero_reuse = {
        "semantic_valid": False,
        "search_aid": True,
        "supported_line": None,
        "situation": "",
        "source": ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_0369.MOV",
        "material_id": "img0369-zero",
        "source_duration_seconds": 14.0,
        "classification_folder": "設置風景",
        "visual": visual("product", "wide", "car"),
        "alternate_ranges": [(2.8, 6.4), (8.0, 12.0)],
    }
    rib_line = "骨組みは頼れる10本骨構造！"
    rib_sit = "裏面の頑丈な10本の骨組みをしっかり見せる商品単体カット"
    old_rib = select_cut([hot], line=rib_line, intended_scenario=rib_sit, duration_seconds=2.0)
    new_rib = select_cut([hot, ribs], line=rib_line, intended_scenario=rib_sit, duration_seconds=2.0)
    check("old-ribs-alias-picks-hot-cabin", old_rib.get("selection", {}).get("material_id") == "hot-cabin")
    check("new-ribs-picks-visible-frame", new_rib.get("selection", {}).get("material_id") == "ribs")
    v_line = "上部V字カットでミラー周りも綺麗！"
    v_sit = "ルームミラーの支柱をきれいに逃がしている上部V字カットの寄り"
    new_v = select_cut([hot, zero_reuse, vcut], line=v_line, intended_scenario=v_sit, duration_seconds=2.0)
    check("new-vcut-picks-visible-v-and-mirror", new_v.get("selection", {}).get("material_id") == "vcut")
    pack_line = "収納ポーチにサッとしまえるよ！"
    pack_sit = "コンパクトになった本体を付属の収納ポーチへ滑り込ませる手元"
    new_pack = select_cut([hot, pouch], line=pack_line, intended_scenario=pack_sit, duration_seconds=2.5)
    check("new-storage-picks-pouch-or-fold", new_pack.get("selection", {}).get("material_id") == "pouch")
    uv_line = "UVカット率約99％！"
    uv_sit = "サンシェードで直射と紫外線を遮っている様子"
    new_uv = select_cut([hot, uv], line=uv_line, intended_scenario=uv_sit, duration_seconds=2.5)
    check("new-uv-does-not-treat-hot-cabin-as-match", new_uv.get("selection", {}).get("material_id") == "uv-shade")
    script = {
        "cuts": [
            {"cut_id": "c8", "line": "毎日の設置がめちゃくちゃ簡単！", "situation": "サンシェードをフロントガラスへ広げている"},
            {"cut_id": "c9", "line": v_line, "situation": v_sit},
        ]
    }
    manifest = {
        "clips": [
            {
                "cut_id": "c8",
                "line": "毎日の設置がめちゃくちゃ簡単！",
                "audio_path": "a.mp3",
                "source_duration_seconds": 3.0,
                "editor_playback_rate": 1.2,
                "planned_duration_seconds": 2.5,
                "source_already_accelerated": False,
            },
            {
                "cut_id": "c9",
                "line": v_line,
                "audio_path": "b.mp3",
                "source_duration_seconds": 3.0,
                "editor_playback_rate": 1.2,
                "planned_duration_seconds": 2.5,
                "source_already_accelerated": False,
            },
        ]
    }
    install_a["alternate_ranges"] = [(2.8, 6.4), (8.0, 12.0)]
    install_b["alternate_ranges"] = [(2.8, 6.4), (8.0, 12.0)]
    plan = assemble_plan(
        script,
        manifest,
        {"c8": [zero_reuse, install_b, hot], "c9": [zero_reuse, install_a, hot]},
    )
    check("same-source-plan-ok", plan.get("status") == "OK", str(plan.get("hold")))
    ranges = [(cut.get("source_in"), cut.get("source_out"), cut.get("material_id")) for cut in plan.get("cuts") or []]
    check("same-img0369-does-not-repeat-zero-range", all(item[0] not in (0.0, None) or "zero" not in str(item[2]) for item in ranges))
    used = {(cut.get("source_in"), cut.get("source_out")) for cut in plan.get("cuts") or []}
    check("same-img0369-uses-different-ranges", len(used) == 2, str(ranges))
    history = {
        "schema": "product_video_approved_shot_history.v1",
        "shots": [
            {
                "source": ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_3893.MOV",
                "in_sec": 0.05,
                "out_sec": 2.17,
                "line": "上部がV字カットになってるから",
                "situation": "ルームミラーの支柱をきれいに逃がしている上部V字カットの寄り",
                "semantic_tags": ["V字カット", "ルームミラー"],
                "visual": visual("product", "wide", "parking"),
            }
        ],
    }
    operator = select_cut(
        [hot, zero_reuse],
        line=v_line,
        intended_scenario=v_sit,
        duration_seconds=2.0,
        history=history,
    )
    check("operator-history-beats-generic-alias", operator.get("selection", {}).get("from_approved_history") is True)
    check("operator-history-keeps-range", operator.get("selection", {}).get("source_in") == 0.05)


def _manifest_clip(cut_id: str, line: str, source_duration: float = 3.6) -> dict[str, Any]:
    return {
        "cut_id": cut_id,
        "line": line,
        "audio_path": f"{cut_id}.mp3",
        "source_duration_seconds": source_duration,
        "editor_playback_rate": 1.2,
        "planned_duration_seconds": source_duration / 1.2,
        "source_already_accelerated": False,
    }


def test_semantic_fallback_matcher(root: Path) -> None:
    sauna_line = "夏場の車内、サウナ状態になってない？"
    sauna_sit = "強い日差しに照らされた車内のハンドルに触れようとして『熱っ！』と手を引っ込める人物"
    bones_line = "10本骨構造だからしっかり張れて崩れない"
    bones_sit = "骨組み部分を見せる"
    v_line = "V字カットでミラーを避ける"
    v_sit = "上部V字がルームミラーを避けている"
    pack_line = "収納ポーチにまとまる"
    pack_sit = "本体をポーチへしまう"

    hot = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/車内暑い/IMG_3948.mov",
        source_in=3.5,
        source_out=7.0,
        objects=["熱い"],
        actions=["手を引く"],
        description="人物がハンドルに触れて「熱っ！」という反応で手を引く",
    )
    vcut = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/vcut.mov",
        source_in=1.0,
        source_out=5.0,
        objects=["切り欠き"],
        features=["上部の切り欠き"],
        description="上部がミラー支柱を避けるように切り欠かれている",
    )
    pouch = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/コンパクト収納/pouch.mov",
        source_in=0.5,
        source_out=4.5,
        objects=["ポーチ"],
        actions=["しまう"],
        description="折りたたんだ本体をポーチへ滑り込ませる",
    )
    ribs = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_3963.mov",
        source_in=0.6,
        source_out=3.16,
        objects=["骨組み", "10本骨"],
        features=["10本骨"],
        description="裏面の頑丈な10本の骨組みが見える",
    )
    hot_id = make_scene_id(hot["source"], 3.5, 7.0)
    v_id = make_scene_id(vcut["source"], 1.0, 5.0)
    pouch_id = make_scene_id(pouch["source"], 0.5, 4.5)
    check(
        "semantic-a-not-deterministic",
        scene_match_score(hot["catalog_scene"], sauna_line, sauna_sit) == 0,
    )
    check(
        "semantic-c-not-deterministic",
        scene_match_score(vcut["catalog_scene"], v_line, v_sit) == 0,
    )

    def script_for(cut_id: str, line: str, situation: str) -> dict[str, Any]:
        return {"cuts": [{"cut_id": cut_id, "line": line, "situation": situation}]}

    def manifest_for(cut_id: str, line: str) -> dict[str, Any]:
        return {"clips": [_manifest_clip(cut_id, line)]}

    calls_a: list[str] = []

    def send_a(prompt: str) -> str:
        calls_a.append(prompt)
        return json.dumps(
            {
                "c1": {
                    "scene_id": hot_id,
                    "source": hot["source"],
                    "source_in": 3.5,
                    "source_out": 7.0,
                    "reason": "高温の車内を熱いハンドルへの反応で表現",
                }
            },
            ensure_ascii=False,
        )

    case_id = "pv-AN-S998-semantic"
    (root / "outputs" / case_id).mkdir(parents=True, exist_ok=True)
    plan_a = assemble_plan(
        script_for("c1", sauna_line, sauna_sit),
        manifest_for("c1", sauna_line),
        {"c1": [hot]},
        semantic_match_fn=send_a,
        project_root=root,
        case_id=case_id,
    )
    check("semantic-a-match", plan_a.get("status") == "OK", str(plan_a.get("hold")))
    check("semantic-a-picks-hot-handle", "IMG_3948.mov" in str((plan_a.get("cuts") or [{}])[0].get("source")))
    check("semantic-a-marks-fallback", (plan_a.get("cuts") or [{}])[0].get("from_semantic_fallback") is True)
    check("semantic-a-one-call", len(calls_a) == 1)
    saved = json.loads((root / "outputs" / case_id / "semantic-material-match.json").read_text(encoding="utf-8"))
    check("semantic-a-persists", saved.get("c1", {}).get("scene_id") == hot_id)

    calls_b: list[str] = []

    def send_b(prompt: str) -> str:
        calls_b.append(prompt)
        return "{}"

    plan_b = assemble_plan(
        script_for("c8", bones_line, bones_sit),
        manifest_for("c8", bones_line),
        {"c8": [hot]},
        semantic_match_fn=send_b,
    )
    check("semantic-b-no-match", plan_b.get("status") == "HOLD")
    check("semantic-b-called-once", len(calls_b) == 1)

    calls_c: list[str] = []

    def send_c(prompt: str) -> str:
        calls_c.append(prompt)
        return json.dumps(
            {
                "c7": {
                    "scene_id": v_id,
                    "source": vcut["source"],
                    "source_in": 1.0,
                    "source_out": 5.0,
                    "reason": "V字とルームミラーが見える",
                }
            },
            ensure_ascii=False,
        )

    plan_c = assemble_plan(
        script_for("c7", v_line, v_sit),
        manifest_for("c7", v_line),
        {"c7": [vcut]},
        semantic_match_fn=send_c,
    )
    check("semantic-c-match", plan_c.get("status") == "OK", str(plan_c.get("hold")))
    check("semantic-c-picks-vcut", (plan_c.get("cuts") or [{}])[0].get("from_semantic_fallback") is True)

    calls_d: list[str] = []

    def send_d(prompt: str) -> str:
        calls_d.append(prompt)
        return "{}"

    plan_d = assemble_plan(
        script_for("c9", pack_line, pack_sit),
        manifest_for("c9", pack_line),
        {"c9": [hot]},
        semantic_match_fn=send_d,
    )
    check("semantic-d-no-match", plan_d.get("status") == "HOLD")
    check("semantic-d-called-once", len(calls_d) == 1)

    calls_e: list[str] = []

    def send_e(prompt: str) -> str:
        calls_e.append(prompt)
        raise AssertionError("deterministic cut must not call Gemini")

    plan_e = assemble_plan(
        script_for("c8", bones_line, "裏面の頑丈な10本の骨組みをしっかり見せる商品単体カット"),
        {"clips": [_manifest_clip("c8", bones_line, source_duration=2.4)]},
        {"c8": [ribs]},
        semantic_match_fn=send_e,
    )
    check("semantic-e-deterministic-ok", plan_e.get("status") == "OK", str(plan_e.get("hold")))
    check("semantic-e-no-gemini", calls_e == [])
    check("semantic-e-not-fallback", (plan_e.get("cuts") or [{}])[0].get("from_semantic_fallback") is not True)

    calls_f: list[str] = []

    def send_f(prompt: str) -> str:
        calls_f.append(prompt)
        return json.dumps(
            {
                "c1": {
                    "scene_id": hot_id,
                    "source": hot["source"],
                    "source_in": 3.5,
                    "source_out": 7.0,
                    "reason": "高温の車内",
                },
                "c7": {
                    "scene_id": v_id,
                    "source": vcut["source"],
                    "source_in": 1.0,
                    "source_out": 5.0,
                    "reason": "V字",
                },
                "c9": {
                    "scene_id": pouch_id,
                    "source": pouch["source"],
                    "source_in": 0.5,
                    "source_out": 4.5,
                    "reason": "収納",
                },
            },
            ensure_ascii=False,
        )

    plan_f = assemble_plan(
        {
            "cuts": [
                {"cut_id": "c1", "line": sauna_line, "situation": sauna_sit},
                {"cut_id": "c7", "line": v_line, "situation": v_sit},
                {"cut_id": "c9", "line": "使わないときはサッとしまえる", "situation": "本体を袋へ収める"},
            ]
        },
        {
            "clips": [
                _manifest_clip("c1", sauna_line),
                _manifest_clip("c7", v_line),
                _manifest_clip("c9", "使わないときはサッとしまえる"),
            ]
        },
        {
            "c1": [hot, vcut, pouch],
            "c7": [hot, vcut, pouch],
            "c9": [hot, vcut, pouch],
        },
        semantic_match_fn=send_f,
    )
    check("semantic-f-batch-ok", plan_f.get("status") == "OK", str(plan_f.get("hold")))
    check("semantic-f-one-batch-call", len(calls_f) == 1)
    if calls_f:
        check("semantic-f-prompt-has-three-cuts", all(token in calls_f[0] for token in ("c1", "c7", "c9")))

    folder_only = {
        "semantic_valid": False,
        "search_aid": False,
        "source": ".runtime/product-video-inputs/AN-S182_コピー/車内暑い/IMG_0001.MOV",
        "objects": ["車内暑い"],
        "scenario_tags": ["車内暑い"],
        "source_duration_seconds": 12.0,
        "available_duration": 12.0,
    }
    payloads = collect_scene_payloads({"c1": [folder_only, hot]}, ["c1"])
    check("semantic-skips-folder-only", payloads and all("IMG_3948.mov" in str(item.get("source")) for item in payloads))
    check("semantic-keeps-catalog-text", any("熱っ" in str(item.get("factual_description")) for item in payloads))
    if calls_a:
        check("semantic-prompt-skips-folder-clip", "IMG_0001.MOV" not in calls_a[0])

    calls_g: list[str] = []

    def send_g(prompt: str) -> str:
        calls_g.append(prompt)
        return (
            "```json\n"
            + json.dumps(
                {
                    "c1": {
                        "scene_id": "IMG_3948.mov|3.500|7.000",
                        "source": "IMG_3948.mov",
                        "source_in": "3.5",
                        "source_out": "7.0",
                        "reason": "高温の車内を熱いハンドルへの反応で表現",
                    }
                },
                ensure_ascii=False,
            )
            + "\n```"
        )

    plan_g = assemble_plan(
        script_for("c1", sauna_line, sauna_sit),
        manifest_for("c1", sauna_line),
        {"c1": [hot]},
        semantic_match_fn=send_g,
    )
    check("semantic-g-string-numbers", plan_g.get("status") == "OK", str(plan_g.get("hold")))
    check("semantic-g-picks-hot-handle", "IMG_3948.mov" in str((plan_g.get("cuts") or [{}])[0].get("source")))
    parsed_g = parse_semantic_matches(
        send_g("unused"),
        scenes=collect_scene_payloads({"c1": [hot]}, ["c1"]),
    )
    check("semantic-g-resolves-basename", parsed_g.get("c1", {}).get("scene_id") == hot_id)

    long_ribs = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_3963.mov",
        source_in=0.0,
        source_out=5.0,
        objects=["フレーム"],
        features=["均等に張った骨"],
        description="裏面の骨が均等に張ってへたらない",
    )
    long_id = make_scene_id(long_ribs["source"], 0.0, 5.0)
    calls_h: list[str] = []

    def send_h(prompt: str) -> str:
        calls_h.append(prompt)
        return json.dumps(
            {
                "c8": {
                    "scene_id": long_id,
                    "source": long_ribs["source"],
                    "source_in": 0.0,
                    "source_out": 5.0,
                    "reason": "骨が張っている",
                }
            },
            ensure_ascii=False,
        )

    plan_h = assemble_plan(
        script_for("c8", bones_line, bones_sit),
        {"clips": [_manifest_clip("c8", bones_line, source_duration=4.8)]},
        {"c8": [ribs, long_ribs]},
        semantic_match_fn=send_h,
    )
    check("semantic-h-short-token-still-fallback", len(calls_h) == 1, str(plan_h.get("hold")))
    check("semantic-h-picks-long-ribs", plan_h.get("status") == "OK" and (plan_h.get("cuts") or [{}])[0].get("from_semantic_fallback") is True)


def test_minimal_range_padding() -> None:
    line_a = "チタンシルバーコーティングで日差しを跳ね返す！"
    sit_a = "ギラギラ光るチタンシルバーの表面を斜め下から見上げるアングル"
    titanium = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_3894.MOV",
        source_in=4.0,
        source_out=7.2,
        objects=["チタンシルバー"],
        features=["生地表面"],
        description="ギラギラした日光を跳ね返すチタンシルバーの生地表面のアップ",
        duration=10.433,
    )
    padded_a = apply_minimal_range_padding(titanium, 3.36)
    check("pad-a-pass", duration_passes(padded_a, 3.36) is True)
    check("pad-a-extends-out", abs(float(padded_a.get("source_out") or 0) - 7.36) < 1e-9)
    check("pad-a-keeps-in", abs(float(padded_a.get("source_in") or 0) - 4.0) < 1e-9)
    selected_a = select_cut([titanium], line=line_a, intended_scenario=sit_a, duration_seconds=3.36)
    check("pad-a-select-ok", selected_a.get("status") == "OK", str(selected_a.get("hold")))
    check("pad-a-select-out", abs(float((selected_a.get("selection") or {}).get("source_out") or 0) - 7.36) < 1e-9)

    line_b = "10本骨構造だからしっかり張れて崩れない"
    sit_b = "傘の骨組み部分を軽く触って頑丈さを見せる手元"
    ribs = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/IMG_3963.mov",
        source_in=0.6,
        source_out=3.72,
        objects=["10本骨"],
        features=["骨組み"],
        description="裏側の10本の金属フレームを指で軽く弾いて丈夫さを見せる手元",
        duration=3.885,
    )
    padded_b = apply_minimal_range_padding(ribs, 3.24)
    check("pad-b-pass", duration_passes(padded_b, 3.24) is True)
    check("pad-b-extends-out", abs(float(padded_b.get("source_out") or 0) - 3.84) < 1e-9)
    check("pad-b-keeps-in", abs(float(padded_b.get("source_in") or 0) - 0.6) < 1e-9)
    selected_b = select_cut([ribs], line=line_b, intended_scenario=sit_b, duration_seconds=3.24)
    check("pad-b-select-ok", selected_b.get("status") == "OK", str(selected_b.get("hold")))

    tiny = _catalog_candidate(
        ".runtime/product-video-inputs/AN-S182_コピー/設置風景/short.mov",
        source_in=1.0,
        source_out=2.0,
        objects=["チタンシルバー"],
        description="チタンシルバーの表面",
        duration=12.0,
    )
    padded_c = apply_minimal_range_padding(tiny, 3.0)
    check("pad-c-no-large-gap", padded_c.get("range_padded") is not True)
    check("pad-c-still-short", duration_passes(padded_c, 3.0) is False)

    short_file = dict(titanium)
    short_file["source_duration_seconds"] = 3.0
    padded_d = apply_minimal_range_padding(short_file, 3.36)
    check("pad-d-no-short-file", padded_d.get("range_padded") is not True)
    check("pad-d-still-short", duration_passes(padded_d, 3.36) is False)

    unmatched = {
        "search_aid": True,
        "semantic_valid": False,
        "source": titanium["source"],
        "source_in": 4.0,
        "source_out": 7.2,
        "source_duration_seconds": 10.433,
        "visual": visual("product", "close", "cabin"),
    }
    padded_e = apply_minimal_range_padding(unmatched, 3.36)
    check("pad-e-no-unmatched", padded_e.get("range_padded") is not True)
    held = select_cut([unmatched], line=line_a, intended_scenario=sit_a, duration_seconds=3.36)
    check("pad-e-does-not-rescue", held.get("status") == "HOLD")

    original = (4.0, 7.2)
    window = (float(padded_a["source_in"]), float(padded_a["source_out"]))
    check("pad-f-contains-original", window[0] <= original[0] + 1e-9 and window[1] + 1e-9 >= original[1])


def test_caption_wrap() -> None:
    uv = wrap_caption("UVカット率はなんと約99パーセント！")
    wrapped = uv.get("caption_visual_wrap") or ""
    check("wrap-keeps-frozen", unwrap_visual(wrapped) == "UVカット率はなんと約99パーセント！")
    check("wrap-does-not-split-uv", "UV\n" not in wrapped)
    check("wrap-does-not-split-percent", "99\nパーセント" not in wrapped and "99\n％" not in wrapped)
    titanium = wrap_caption("チタンシルバーの特殊コーティング採用！")
    check("wrap-does-not-split-titanium", "チタン\nシルバー" not in (titanium.get("caption_visual_wrap") or ""))
    particle = wrap_caption("夏場の車内、熱すぎて触れない人これ見て！")
    lines = (particle.get("caption_visual_wrap") or "").split("\n")
    check("wrap-no-one-char-line", all(len(line) != 1 for line in lines))
    check("wrap-no-particle-only-line", all(line not in {"は", "が", "を", "に", "で", "と", "も", "の"} for line in lines))
    shade = wrap_caption("吸盤がすぐ落ちるサンシェード、もう限界…")
    check("wrap-comma-stays-with-clause", (shade.get("caption_visual_wrap") or "").startswith("吸盤がすぐ落ちるサンシェード、"))
    many = wrap_caption("ミラー周りが浮いちゃうこと多くない？")
    check("wrap-does-not-split-ookunai", "多\nくない" not in (many.get("caption_visual_wrap") or ""))
    once = wrap_caption("これなら折りたたみ傘感覚で一発装着！")
    check("wrap-does-not-split-ippatsu", "一\n発" not in (once.get("caption_visual_wrap") or ""))
    block = wrap_caption("日差しや紫外線をしっかりブロック！")
    check("wrap-does-not-split-block", "ブロ\nック" not in (block.get("caption_visual_wrap") or ""))
    sag = wrap_caption("頑丈な10本骨だからへたりにくい！")
    check("wrap-does-not-split-hetari", "へたりに\nくい" not in (sag.get("caption_visual_wrap") or ""))
    pouch = wrap_caption("ポーチへスリムに収まって場所を取らない！")
    check("wrap-break-after-te", (pouch.get("caption_visual_wrap") or "").startswith("ポーチへスリムに収まって\n"))
    vcut = wrap_caption("こだわりのV字カット加工で…")
    vwrap = vcut.get("caption_visual_wrap") or ""
    check("wrap-keeps-vcut-phrase", "V字\nカット" not in vwrap and "V字カット" in vwrap)
    check("wrap-before-protected-compound", vwrap.startswith("こだわりの\n"))
    measure = wrap_caption("UV約99パーセントカット＆UPF40以上！")
    mwrap = measure.get("caption_visual_wrap") or ""
    check("wrap-keeps-percent-unit", "約99\nパーセント" not in mwrap and mwrap.startswith("UV約99パーセント\n"))
    check("wrap-keeps-upf-unit", "UPF40以上" in mwrap and "UPF\n" not in mwrap)
    short_ok = wrap_caption("下からチェック！")
    check("wrap-keeps-short-line", (short_ok.get("caption_visual_wrap") or "") == "下からチェック！")
    last_lines = (wrap_caption("チタンシルバーの特殊コーティング採用！").get("caption_visual_wrap") or "").split("\n")
    check("wrap-no-tiny-last-line", all(len(line) > 2 for line in last_lines))


def test_timing_metrics(root: Path) -> None:
    case_id = "pv-AN-S999-timing"
    (root / "outputs" / case_id / "receipts").mkdir(parents=True)
    (root / "outputs" / case_id / "receipts" / "picture_swap_c1.json").write_text("{}", encoding="utf-8")
    mark_stage_start(root, case_id, "SCRIPT")
    mark_stage_end(root, case_id, "SCRIPT")
    mark_stage_start(root, case_id, "NARRATION")
    mark_stage_end(root, case_id, "NARRATION", receipt={"clip_count": 2})
    mark_stage_start(root, case_id, "ASSEMBLY")
    mark_stage_end(root, case_id, "ASSEMBLY")
    mark_stage_start(root, case_id, "ROUGH_EDIT")
    mark_stage_end(root, case_id, "ROUGH_EDIT")
    mark_stage_start(root, case_id, "DELIVERY")
    mark_stage_end(root, case_id, "DELIVERY")
    summary = summarize(load_timing(root, case_id))
    check("timing-has-script", isinstance(summary.get("script_elapsed_seconds"), float))
    check("timing-has-narration", isinstance(summary.get("narration_elapsed_seconds"), float))
    check("timing-cut-count", summary.get("cut_count") == 2)
    check("timing-avg-tts", isinstance(summary.get("avg_tts_seconds_per_cut"), float))
    check("timing-assembly", isinstance(summary.get("assembly_plan_elapsed_seconds"), float))
    check("timing-chatcut", isinstance(summary.get("chatcut_placement_elapsed_seconds"), float))
    check("timing-picture-swaps", summary.get("human_picture_swap_count") == 1)
    check("timing-export-drive", isinstance(summary.get("export_drive_elapsed_seconds"), float))
    recorded = record_rough_edit_metrics(
        root,
        case_id,
        {
            "chatcut_project_setup_seconds": 1.0,
            "import_seconds": 2.0,
            "place_audio_seconds": 3.0,
            "playback_rate_seconds": 4.0,
            "place_video_seconds": 5.0,
            "caption_preset_seconds": 6.0,
            "place_captions_seconds": 7.0,
            "final_verify_seconds": 8.0,
        },
    )
    check("timing-rough-steps-recorded", recorded.get("status") == "OK")
    loaded = load_timing(root, case_id)
    metrics = loaded.get("metrics") or {}
    for key in ROUGH_EDIT_METRIC_KEYS:
        check(f"timing-has-{key}", isinstance(metrics.get(key), float), key)
    check("timing-rough-total-from-stage", metrics.get("rough_edit_total_seconds") == summary.get("chatcut_placement_elapsed_seconds"))


def test_dispatch_initial_entry(root: Path) -> None:
    """No case_id and no active case: preflight first, then PREPARE, no NameError."""
    outputs = root / "outputs"
    preexisting = [p.name for p in outputs.iterdir()] if outputs.is_dir() else []
    check("initial-entry-no-active-case", preexisting == [], str(preexisting))
    try:
        blocked = dispatch(root, product_model="AN-S999")
    except Exception as exc:  # noqa: BLE001
        check("initial-entry-no-exception", False, f"{type(exc).__name__}: {exc}")
        return
    check("initial-entry-no-exception", True)
    check("initial-entry-action", blocked.get("action") == "run_preflight")
    check("initial-entry-no-case-before-preflight", blocked.get("create_case") is False)
    cases_blocked = sorted(p.name for p in outputs.iterdir() if p.is_dir()) if outputs.is_dir() else []
    check("initial-entry-no-case-yet", cases_blocked == [], str(cases_blocked))
    try:
        first = dispatch(root, product_model="AN-S999", preflight_ready=True)
    except Exception as exc:  # noqa: BLE001
        check("initial-entry-ready-no-exception", False, f"{type(exc).__name__}: {exc}")
        return
    check("initial-entry-ready-no-exception", True)
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


def test_preflight_operator_batch(root: Path) -> None:
    helper = subprocess.run(
        [sys.executable, str(helper_path(REPO, "run_preflight")), "--self-test"],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
    )
    check("preflight-helper-self-test", helper.returncode == 0, (helper.stdout or helper.stderr or "")[-400:])
    calls = {"n": 0}

    def flaky() -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] < 2:
            return {"status": "HOLD", "hold": HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE}
        return {"status": "OK"}

    recovered = retry_call(flaky, attempts=3)
    check("preflight-retry-recovers", recovered.get("status") == "OK")
    batched = merge_preflight(
        [
            item("chrome_local", {"status": "HOLD", "hold": HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE}, operator_fix="Chrome remote debugging OFF"),
            item("drive", {"status": "HOLD", "hold": "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE"}, operator_fix="Drive OAuth期限切れ"),
        ]
    )
    check("preflight-batch-hold", batched.get("hold") == HOLD_PREFLIGHT_REQUIRED)
    check("preflight-batch-two", batched.get("operator_fixes") == ["Chrome remote debugging OFF"])
    check("preflight-batch-drive-deferred", batched.get("delivery_ready") is False)

    observation = {
        "chrome_mcp_attached": True,
        "capcut_tts_reachable": True,
        "capcut_logged_in": True,
        "holiday_twist_available": True,
        "chatcut_connected": True,
    }
    payload = run_preflight(
        root,
        product_model="AN-S999",
        observation=observation,
        live=False,
        gemini_probe_fn=lambda: {"status": "OK", "model_required": "gemini-3.8-flash"},
        gemini_print_fn=lambda: {"status": "OK", "last_text": "PONG"},
        chrome_fn=lambda: {"status": "OK"},
        drive_fn=lambda: {"status": "OK"},
    )
    check("preflight-fake-project-ready", payload.get("status") == "READY", str(payload.get("hold")))
    check("preflight-no-writes", payload.get("writes") is False and payload.get("tts_generated") is False)
    check("preflight-delivery-ready-when-drive-ok", payload.get("delivery_ready") is True)

    mcp_only = run_preflight(
        root,
        product_model="AN-S999",
        observation={
            "chrome_mcp_attached": False,
            "chatcut_connected": True,
        },
        live=False,
        gemini_probe_fn=lambda: {"status": "OK", "model_required": "gemini-3.8-flash"},
        gemini_print_fn=lambda: {"status": "OK", "last_text": "PONG"},
        chrome_fn=lambda: {"status": "OK", "remote_debugging": "READY", "port": 9222},
        drive_fn=lambda: {"status": "OK"},
    )
    message = mcp_only.get("message_ja") or ""
    check("mcp-fail-holds", mcp_only.get("status") == "HOLD")
    check("mcp-fail-not-rd-off", "remote debugging を許可する" not in message and "Remote Debuggingを許可" not in message)
    check("mcp-fail-records-attach", "Playwright MCP attach失敗" in message)
    check("mcp-fail-chrome-ready", "Chrome 9222 READY" in message)

    case_id = "pv-AN-S999-held"
    materials = root / ".runtime" / "product-video-inputs" / "AN-S999_コピー"
    seed_state(
        root,
        case_id,
        "NARRATION",
        ["PREPARE", "SCRIPT", "SCRIPT_SELECTION"],
        extra={
            "material_root": str(materials),
            "selected_script_variant": 2,
            "hold": {"code": HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE, "stage": "NARRATION"},
        },
    )
    blocked = dispatch(root, case_id=case_id, product_model="AN-S999")
    check("held-case-reruns-preflight", blocked.get("action") == "run_preflight")
    check("held-case-preserved", blocked.get("preserve_case") is True and blocked.get("case_id") == case_id)
    check("held-case-stays-narration", blocked.get("current_stage") == "NARRATION")
    resumed = dispatch(root, case_id=case_id, product_model="AN-S999", preflight_ready=True)
    check("held-case-resumes-narration", resumed.get("skill") == "product-video-narration" and resumed.get("stage") == "NARRATION")
    state = load_state(root, case_id)
    check("held-case-hold-cleared", state.get("hold") is None)
    check("held-case-variant-kept", state.get("selected_script_variant") == 2)
    check(
        "held-case-stages-kept",
        state.get("completed_stages") == ["PREPARE", "SCRIPT", "SCRIPT_SELECTION"],
    )
    cleared = clear_hold(root, case_id)
    check("clear-hold-keeps-stage", cleared.get("current_stage") == "NARRATION")


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
        verified_facts=["車内の日差しを遮るサンシェード", "傘型でパッと開く"],
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
    (root / "outputs" / case_id / "gemini-output.txt").write_text(grounded_sample_scripts(3), encoding="utf-8")
    stored = accept_gemini_output(root, case_id, grounded_sample_scripts(3))
    check("script-stops-for-selection", stored.get("current_stage") == "SCRIPT_SELECTION")
    check("script-hides-evidence-ids", "evidence_ids" not in json.dumps(stored.get("operator_variants") or []))
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
    delivery = dispatch(
        root,
        case_id=case_id,
        utterance=DELIVERY_APPROVAL,
        drive_fn=lambda: {"status": "OK"},
    )
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
        inputs = json.loads(
            (root / "outputs" / created["case_id"] / "product-inputs.json").read_text(encoding="utf-8")
        )
        check(
            "prepare-F-inputs-have-facts",
            "車内の日差しを遮るサンシェード" in (inputs.get("product_information") or "")
            and "装着が簡単" in (inputs.get("product_appeal_points") or "")
            and "車内の日差しを遮るサンシェード" in (inputs.get("verified_facts") or []),
        )


def test_product_facts_prepare(root: Path) -> None:
    completed = []
    outputs = REPO / "outputs"
    if outputs.is_dir():
        for path in sorted(outputs.glob("pv-*/product-inputs.json")):
            state = path.parent / "workflow-state.json"
            completed.append(
                (
                    path.as_posix(),
                    path.read_bytes(),
                    state.read_bytes() if state.is_file() else b"",
                )
            )

    loaded = load_product_facts_profile(REPO, "AN-S182")
    check("facts-A-an-s182-pass", loaded.get("status") == "OK", str(loaded))
    check("facts-A-usable-at-least-3", int(loaded.get("usable_fact_count") or 0) >= 3)
    check(
        "facts-A-expected-path",
        loaded.get("expected_facts_profile_path") == facts_path_for(REPO, "AN-S182").as_posix(),
    )
    usable_texts = " ".join(loaded.get("verified_facts") or []) + " " + " ".join(loaded.get("appeal_points") or [])
    check("facts-C-profile-has-no-jan-asin-model-as-required-count", "JAN" not in usable_texts and "ASIN" not in usable_texts)

    identifiers_only = prove_usable_product_facts(
        "- 製品型番はAN-S182\n- JAN 4901234567890\n- ASIN B0ABCDEFGH\n- CTAは「下からチェック！」",
        "",
        product_model="AN-S182",
        facts_path=facts_path_for(REPO, "AN-S182"),
    )
    check("facts-B-model-cta-holds", identifiers_only.get("hold") == HOLD_PRODUCT_FACTS_REQUIRED)
    check("facts-B-count-zero", identifiers_only.get("usable_fact_count") == 0)
    check("facts-B-has-model", identifiers_only.get("product_model") == "AN-S182")
    check(
        "facts-B-has-path",
        identifiers_only.get("expected_facts_profile_path") == facts_path_for(REPO, "AN-S182").as_posix(),
    )

    two_real = prove_usable_product_facts(
        "- 製品型番はAN-S182\n- JAN 4901234567890\n- ASIN B0ABCDEFGH\n- 折りたたみ傘のように開いてフロントガラス内側へ設置できる",
        "- 傘のようにパッと開いて設置しやすい",
        product_model="AN-S182",
        facts_path=facts_path_for(REPO, "AN-S182"),
    )
    check("facts-C-identifiers-not-counted", two_real.get("usable_fact_count") == 2)
    check("facts-C-identifiers-hold", two_real.get("hold") == HOLD_PRODUCT_FACTS_REQUIRED)

    missing = load_product_facts_profile(root, "AN-Z001")
    check("facts-D-missing-holds", missing.get("hold") == HOLD_PRODUCT_FACTS_REQUIRED)
    check("facts-D-count-zero", missing.get("usable_fact_count") == 0)
    check(
        "facts-D-path",
        missing.get("expected_facts_profile_path") == facts_path_for(root, "AN-Z001").as_posix(),
    )

    thin = {
        "schema_version": "1",
        "product_model": "AN-S998",
        "verified_facts": ["製品型番はAN-S998", "JAN 4901234567890"],
        "appeal_points": [],
    }
    settings = {
        "schema_version": "1",
        "status": "active",
        "product_model": "AN-S998",
        "cta": {"text": "下からチェック！", "literal_match_required": True},
    }
    (root / "config" / "product_video_settings_AN-S998.v1.json").write_text(
        json.dumps(settings, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "config" / "product_video_product_facts_AN-S998.v1.json").write_text(
        json.dumps(thin, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / ".runtime" / "product-video-inputs" / "AN-S998_コピー").mkdir(parents=True)
    (root / ".runtime" / "product-video-inputs" / "AN-S998_コピー" / "clip.mov").write_bytes(b"not-a-real-video")
    campaign_only = create_new_case(root, "AN-S998", "夏の車内を涼しく")
    check("facts-E-campaign-does-not-fill", campaign_only.get("hold") == HOLD_PRODUCT_FACTS_REQUIRED)
    check("facts-E-campaign-count", int(campaign_only.get("usable_fact_count") or 0) < 3)

    created = next(
        (
            path
            for path in sorted((root / "outputs").glob("pv-AN-S999-*"), reverse=True)
            if (path / "product-inputs.json").is_file()
        ),
        None,
    )
    check("facts-F-create-ok", created is not None)
    if created is not None:
        inputs = json.loads((created / "product-inputs.json").read_text(encoding="utf-8"))
        check("facts-F-verified-facts", "車内の日差しを遮るサンシェード" in (inputs.get("verified_facts") or []))
        check("facts-F-appeal-points", "装着が簡単" in (inputs.get("appeal_points") or []))
        catalog = build_fact_catalog(inputs.get("product_information") or "", inputs.get("product_appeal_points") or "")
        ids = [item["id"] for item in catalog["facts"]]
        check("facts-G-f-ids-from-profile", "F1" in ids and "F2" in ids and "F3" in ids)
        check(
            "facts-G-f1-from-profile",
            catalog["by_id"]["F1"]["text"] == "車内の日差しを遮るサンシェード",
        )

    after = []
    if outputs.is_dir():
        for path in sorted(outputs.glob("pv-*/product-inputs.json")):
            state = path.parent / "workflow-state.json"
            completed_now = (
                path.as_posix(),
                path.read_bytes(),
                state.read_bytes() if state.is_file() else b"",
            )
            after.append(completed_now)
    check("facts-H-completed-untouched", after == completed)

    settings_only = build_product_inputs(
        {"product_model": "AN-S182", "cta": {"text": "下からチェック！"}},
        verified_facts=[],
        appeal_points=[],
        user_campaign_focus="優先訴求だけ",
    )
    thin_proof = prove_usable_product_facts(
        str(settings_only.get("product_information") or ""),
        str(settings_only.get("product_appeal_points") or ""),
        product_model="AN-S182",
        facts_path=facts_path_for(REPO, "AN-S182"),
    )
    check("facts-B-build-cta-model-holds", thin_proof.get("hold") == HOLD_PRODUCT_FACTS_REQUIRED)
    check("facts-E-focus-not-in-information", "優先訴求だけ" not in (settings_only.get("product_information") or ""))


def _grounding_cut(index: int, line: str, evidence: list[str], situation: str = "手元") -> dict:
    return {
        "cut_id": f"c{index}",
        "index": index,
        "evidence_ids": evidence,
        "situation": situation,
        "line": line,
    }


def _grounding_variant(cuts: list[dict], variant_id: int = 1, title: str = "接地型") -> dict:
    return {"variant_id": variant_id, "title": title, "estimated_seconds": 45, "cuts": cuts}


def test_script_grounding() -> None:
    info = "- 車内の日差しを遮るサンシェード\n- 傘型でパッと開く\n- 製品型番はAN-S182"
    appeals = "- 装着が簡単"
    catalog = build_fact_catalog(info, appeals)
    check(
        "grounding-ids-skip-model",
        [item["id"] for item in catalog["facts"]] == ["F1", "F2", "F3"]
        and catalog["by_id"]["F3"]["text"] == "装着が簡単",
    )
    grounded_cuts = [
        _grounding_cut(1, "車、サウナすぎん？", ["HOOK"], "車内でハンドルを握る人物"),
        _grounding_cut(2, "日差しをサンシェードで遮る", ["F1"], "サンシェードを広げる手元"),
        _grounding_cut(3, "傘型でパッと開く", ["F2"], "傘型サンシェードを開く手元"),
        _grounding_cut(4, "装着が簡単すぎる", ["F3"], "装着する手元"),
        _grounding_cut(5, "下からチェック！", ["CTA"], "画面下を指す"),
    ]
    pass_one = prove_variant_grounding(
        _grounding_variant(grounded_cuts),
        catalog,
        product_information=info,
        product_appeal_points=appeals,
    )
    check("grounding-A-uses-three-facts", pass_one.get("status") == "OK", str(pass_one))
    check("grounding-E-hook-cta-ok", pass_one.get("status") == "OK")
    check("grounding-F-no-model-required", pass_one.get("status") == "OK" and "AN-S182" not in "".join(cut["line"] for cut in grounded_cuts))

    generic_cuts = [
        _grounding_cut(1, "ガチで買って大正解だった", ["HOOK"]),
        _grounding_cut(2, "最近の中で一番の当たり枠", ["HOOK"]),
        _grounding_cut(3, "気になって試してみたら", ["HOOK"]),
        _grounding_cut(4, "下からチェック！", ["CTA"]),
    ]
    generic = prove_variant_grounding(
        _grounding_variant(generic_cuts),
        catalog,
        product_information=info,
        product_appeal_points=appeals,
    )
    check("grounding-B-generic-holds", generic.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING)

    one_id_cuts = list(grounded_cuts)
    one_id_cuts[2] = _grounding_cut(3, "日差しをもう一回遮る", ["F1"], "サンシェード")
    one_id_cuts[3] = _grounding_cut(4, "日差しが違う", ["F1"], "サンシェード")
    one_id = prove_variant_grounding(
        _grounding_variant(one_id_cuts),
        catalog,
        product_information=info,
        product_appeal_points=appeals,
    )
    check("grounding-C-one-fid-holds", one_id.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING)

    hook_only_product = [
        _grounding_cut(1, "日差しをサンシェードで遮る", ["HOOK"], "サンシェードを広げる手元"),
        _grounding_cut(2, "期待を余裕で超えてきた", ["HOOK"]),
        _grounding_cut(3, "シンプルで使い勝手も完璧", ["HOOK"]),
        _grounding_cut(4, "下からチェック！", ["CTA"]),
    ]
    hook_rest = prove_variant_grounding(
        _grounding_variant(hook_only_product),
        catalog,
        product_information=info,
        product_appeal_points=appeals,
    )
    check("grounding-D-hook-then-generic-holds", hook_rest.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING)

    invented = list(grounded_cuts)
    invented[1] = _grounding_cut(2, "日差しカット99パーセント", ["F1"], "サンシェード")
    invented_hold = prove_variant_grounding(
        _grounding_variant(invented),
        catalog,
        product_information=info,
        product_appeal_points=appeals,
    )
    check("grounding-G-invented-number-holds", invented_hold.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING)

    an_info = (
        "- 折りたたみ傘のように開いてフロントガラス内側へ設置できる\n"
        "- UVカット率約99％、UPF40以上\n"
        "- 表面にチタンシルバーコーティングを採用\n"
        "- 上部V字カットでルームミラーへの干渉を避けやすい\n"
        "- 10本骨構造\n"
        "- 使用後はスリムに折りたためて収納ポーチへ収納できる"
    )
    an_appeals = (
        "- 傘のようにパッと開いて設置しやすい\n"
        "- 日差し・紫外線対策に使える\n"
        "- ルームミラー周辺へ合わせやすい\n"
        "- 使わない時はコンパクトに収納しやすい"
    )
    an_catalog = build_fact_catalog(an_info, an_appeals)
    umbrella_fact = next(item["text"] for item in an_catalog["facts"] if "傘" in item["text"] and "開" in item["text"])
    titanium_fact = next(item["text"] for item in an_catalog["facts"] if "チタンシルバー" in item["text"])
    uv_fact = next(item["text"] for item in an_catalog["facts"] if "UV" in item["text"])
    check("grounding-C-umbrella-paraphrase", line_matches_fact("傘みたいにパッと開く", umbrella_fact))
    check("grounding-D-titanium-paraphrase", line_matches_fact("チタンシルバーでガード", titanium_fact))
    check("grounding-E-uv99", line_matches_fact("UV99％", uv_fact))
    check(
        "grounding-paraphrase-not-generic",
        not line_matches_fact("これ便利", umbrella_fact)
        and not line_matches_fact("買って正解", titanium_fact),
    )

    mismatched_cuts = [
        _grounding_cut(1, "車、サウナすぎん？", ["HOOK"]),
        _grounding_cut(2, "チタンシルバーで日差し対策", ["F1"]),
        _grounding_cut(3, "傘みたいにパッと開く", ["F2"]),
        _grounding_cut(4, "UV99％", ["F4"]),
        _grounding_cut(5, "下からチェック！", ["CTA"]),
    ]
    mismatch_ok = prove_variant_grounding(
        _grounding_variant(mismatched_cuts),
        an_catalog,
        product_information=an_info,
        product_appeal_points=an_appeals,
    )
    check("grounding-A-mismatch-still-pass", mismatch_ok.get("status") == "OK", str(mismatch_ok))
    check("grounding-G-three-actual-facts", len(mismatch_ok.get("actual_used_fact_ids") or []) >= 3, str(mismatch_ok))
    check("grounding-mismatch-recorded", bool(mismatch_ok.get("evidence_id_mismatch")), str(mismatch_ok))
    check(
        "grounding-mismatch-not-hold-reason",
        "unrelated" not in str(mismatch_ok.get("reason") or ""),
    )

    labeled_generic = [
        _grounding_cut(1, "これ便利", ["HOOK"]),
        _grounding_cut(2, "買って正解", ["F1"]),
        _grounding_cut(3, "気になって試してみたら", ["F2"]),
        _grounding_cut(4, "最近の中で一番の当たり枠", ["F3"]),
        _grounding_cut(5, "下からチェック！", ["CTA"]),
    ]
    labeled_generic_hold = prove_variant_grounding(
        _grounding_variant(labeled_generic),
        an_catalog,
        product_information=an_info,
        product_appeal_points=an_appeals,
    )
    check("grounding-B-correct-ids-generic-holds", labeled_generic_hold.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING)

    invented_uv = list(mismatched_cuts)
    invented_uv[3] = _grounding_cut(4, "UV100％", ["F2"])
    invented_uv_hold = prove_variant_grounding(
        _grounding_variant(invented_uv),
        an_catalog,
        product_information=an_info,
        product_appeal_points=an_appeals,
    )
    check("grounding-F-uv100-invented-holds", invented_uv_hold.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING, str(invented_uv_hold))

    thin_cuts = [
        _grounding_cut(1, "車、サウナすぎん？", ["HOOK"]),
        _grounding_cut(2, "チタンシルバーでガード", ["F1"]),
        _grounding_cut(3, "買って正解", ["F2"]),
        _grounding_cut(4, "下からチェック！", ["CTA"]),
    ]
    thin_hold = prove_variant_grounding(
        _grounding_variant(thin_cuts),
        an_catalog,
        product_information=an_info,
        product_appeal_points=an_appeals,
    )
    check("grounding-H-one-or-two-facts-hold", thin_hold.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING, str(thin_hold))
    check(
        "grounding-actual-ids-from-line",
        "F3" in actual_facts_for_line("チタンシルバーでガード", an_catalog),
    )

    parsed = parse_gemini_scripts(grounded_sample_scripts(3))
    check("grounding-parser-evidence", parsed.get("status") == "OK" and parsed["variants"][0]["cuts"][0]["evidence_ids"] == ["HOOK"])
    presented = json.dumps(present_for_operator(parsed), ensure_ascii=False)
    check(
        "grounding-H-hide-ids",
        "evidence_ids" not in presented
        and "根拠ID" not in presented
        and "F1" not in presented
        and "actual_fact_ids" not in presented
        and "evidence_id_mismatch" not in presented,
    )

    three = {
        "status": "OK",
        "variant_count": 3,
        "variants": [_grounding_variant(grounded_cuts, variant_id=n, title=f"案{n}") for n in (1, 2, 3)],
    }
    ok_all = prove_scripts_grounding(three, info, appeals)
    check("grounding-A-all-variants-pass", ok_all.get("status") == "OK", str(ok_all))
    generic_batch = {
        "status": "OK",
        "variant_count": 3,
        "variants": [_grounding_variant(generic_cuts, variant_id=n) for n in (1, 2, 3)],
    }
    held_batch = prove_scripts_grounding(generic_batch, info, appeals)
    check("grounding-B-batch-holds", held_batch.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING)

    skill = (REPO / ".cursor" / "skills" / "product-video-script" / "SKILL.md").read_text(encoding="utf-8")
    check("grounding-regen-once", "once more" in skill or "同じ" in skill)
    check("grounding-no-third-regen", "third" in skill or "3" in skill or "再生成" in skill)
    check("grounding-hold-code", HOLD_SCRIPT_PRODUCT_GROUNDING in skill)
    check("grounding-hide-from-operator", "根拠ID" in skill and "Do **not** show" in skill)

    with tempfile.TemporaryDirectory() as raw:
        root = fake_project(Path(raw) / "grounding")
        case_id = "pv-AN-S999-ground"
        materials = root / ".runtime" / "product-video-inputs" / "AN-S999_コピー"
        seed_state(root, case_id, "SCRIPT", ["PREPARE"], extra={"material_root": str(materials)})
        inputs = build_product_inputs(
            {"product_model": "AN-S999", "cta": {"text": "下からチェック！"}},
            verified_facts=["車内の日差しを遮るサンシェード", "傘型でパッと開く"],
            appeal_points=["装着が簡単"],
        )
        (root / "outputs" / case_id / "product-inputs.json").write_text(
            json.dumps(inputs, ensure_ascii=False),
            encoding="utf-8",
        )
        first = accept_gemini_output(root, case_id, sample_scripts(3))
        check("grounding-regen-first", first.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING and first.get("regenerate") is True)
        second = accept_gemini_output(root, case_id, sample_scripts(3))
        check(
            "grounding-regen-second-holds",
            second.get("hold") == HOLD_SCRIPT_PRODUCT_GROUNDING and second.get("regenerate") is False,
        )
        check("grounding-stage-not-complete", load_state(root, case_id)["current_stage"] == "SCRIPT")
        frozen_ok = accept_gemini_output(root, case_id, grounded_sample_scripts(3))
        check("grounding-pass-completes", frozen_ok.get("current_stage") == "SCRIPT_SELECTION", str(frozen_ok.get("hold")))
        check("grounding-attempts-kept-on-pass", load_state(root, case_id).get("script_grounding_attempts") == 2)
        if frozen_ok.get("status") == "OK":
            freeze = freeze_approved_script(root, load_state(root, case_id), 2)
            check("grounding-freeze-ok", freeze.get("status") == "OK")
            approved = json.loads((root / "outputs" / case_id / "approved-script.json").read_text(encoding="utf-8"))
            blob = json.dumps(approved, ensure_ascii=False)
            check("grounding-H-frozen-hides-ids", "evidence_ids" not in blob and "根拠ID" not in blob)


def test_prompt_template() -> None:
    template = load_template(REPO)
    prompt = render_script_prompt(
        template,
        product_information="- 車内の日差しを遮るサンシェード\n- 傘型でパッと開く\n- 製品型番はAN-S182",
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
    check("prompt-requires-evidence-id", "根拠ID" in prompt)
    check("prompt-labels-f1", "F1: 車内の日差しを遮るサンシェード" in prompt)
    check("prompt-labels-f2", "F2: 傘型でパッと開く" in prompt)
    check("prompt-labels-appeal-f3", "F3: 装着が簡単" in prompt)
    check("prompt-keeps-model-unlabeled", "製品型番はAN-S182" in prompt and "F4:" not in prompt)
    check("prompt-model-not-assigned-fid", not re.search(r"F\d+:\s*製品型番はAN-S182", prompt))
    check("prompt-no-runcommand", "RunCommand" not in prompt)


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


def test_gemini_cli_transport() -> None:
    helper = helper_path(REPO, "send_gemini_cli_prompt")
    result = subprocess.run(
        [sys.executable, str(helper), "--self-test"],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
    )
    check("gemini-cli-helper-self-test", result.returncode == 0, (result.stdout or result.stderr or "")[-500:])
    template = (REPO / ".cursor" / "skills" / "product-video" / "references" / "gemini-script-instructions.md").read_text(
        encoding="utf-8"
    )
    check("creative-template-has-no-transport-prefix", "RunCommand" not in template)


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
        ("tts_session", ".cursor/skills/product-video/scripts/tts_session.py"),
        ("approved_shots", ".cursor/skills/product-video/scripts/approved_shots.py"),
        ("narration_queue", ".cursor/skills/product-video/scripts/narration_queue.py"),
        ("material_index", ".cursor/skills/product-video/scripts/material_index.py"),
        ("visual_catalog", ".cursor/skills/product-video/scripts/visual_catalog.py"),
        ("caption_wrap", ".cursor/skills/product-video/scripts/caption_wrap.py"),
        ("edit_plan", ".cursor/skills/product-video/scripts/edit_plan.py"),
        ("semantic_material_match", ".cursor/skills/product-video/scripts/semantic_material_match.py"),
        ("timing", ".cursor/skills/product-video/scripts/timing.py"),
        ("preserve_shared_inputs", ".cursor/skills/product-video/scripts/preserve_shared_inputs.py"),
        ("run_preflight", ".cursor/skills/product-video/scripts/run_preflight.py"),
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
    check("rough-skill-one-pass", "one-pass" in rough_skill and "final_verify" in rough_skill)
    check("rough-skill-no-per-cut-inspect", "Do not call `inspect_item` after each write" in rough_skill)
    check("narration-skill-uses-attempts", "product-video/scripts/tts_attempts.py" in narration_skill)
    check("narration-skill-uses-session", "product-video/scripts/tts_session.py" in narration_skill)
    check(
        "narration-skill-no-legacy-tts",
        "produce-tiktok-product-video-portable/scripts/prove_tts_textarea.py" not in narration_skill,
    )
    assembly_skill = (skills_root / "product-video-assembly" / "SKILL.md").read_text(encoding="utf-8")
    check("assembly-skill-uses-history", "product-video/scripts/approved_shots.py" in assembly_skill)
    check("assembly-skill-uses-visual-catalog", "product-video/scripts/visual_catalog.py" in assembly_skill)
    check("assembly-skill-history-first", "approved-shot history" in assembly_skill)
    delivery_skill = (skills_root / "product-video-delivery" / "SKILL.md").read_text(encoding="utf-8")
    check("delivery-skill-records-history", "approved_shots.py" in delivery_skill and "--record-final" in delivery_skill)
    check("delivery-skill-keeps-history", "product-video-approved-shots" in delivery_skill)
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
    check("chrome-G-retry-then-hold", "retry up to 3" in ref)
    check("chrome-G-narration-reuses-session", "keep that same attached page" in ref)
    check("chrome-G-batch-preflight-fixes", "開始前に直すこと" in ref)
    check("chrome-G-9222-ready-not-rd-off", "127.0.0.1:9222 is already listening" in ref)


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
        helper.PERSISTENT_SHARED_INPUT_ROOTS == PERSISTENT_SHARED_INPUT_ROOTS,
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
        skipped_paths = {item.get("path") for item in payload.get("skipped") or []}
        check("purge-skip-approved-shots-root", ".runtime/product-video-approved-shots" in skipped_paths)
        check("purge-skip-material-metadata-root", ".runtime/product-video-material-metadata" in skipped_paths)
        check("purge-skip-material-index-root", ".runtime/product-video-material-index" in skipped_paths)
        check("purge-skip-visual-catalog-root", ".runtime/product-video-visual-catalog" in skipped_paths)
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


def ready_start_observation(**overrides: Any) -> dict[str, Any]:
    observation = {
        "chrome_mcp_attached": True,
        "capcut_tts_reachable": True,
        "capcut_logged_in": True,
        "holiday_twist_available": True,
        "chatcut_connected": True,
    }
    observation.update(overrides)
    return observation


def test_drive_deferred_preflight(scratch: Path) -> None:
    def drive_ok() -> dict[str, Any]:
        return {"status": "OK"}

    def drive_fail() -> dict[str, Any]:
        return {
            "status": "HOLD",
            "hold": "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE",
            "reason": "refresh failed",
        }

    def start_kwargs(**overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "product_model": "AN-S999",
            "observation": ready_start_observation(),
            "live": False,
            "gemini_probe_fn": lambda: {"status": "OK", "model_required": "gemini-3.8-flash"},
            "gemini_print_fn": lambda: {"status": "OK", "last_text": "PONG"},
            "chrome_fn": lambda: {"status": "OK"},
            "drive_fn": drive_ok,
        }
        kwargs.update(overrides)
        return kwargs

    root = fake_project(scratch / "start")
    drive_only = run_preflight(root, **start_kwargs(drive_fn=drive_fail))
    check("A-drive-only-ready", drive_only.get("status") == "READY", str(drive_only.get("hold")))
    check("A-delivery-not-ready", drive_only.get("delivery_ready") is False)
    check("A-delivery-warning", drive_only.get("delivery_warnings") == [DRIVE_DELIVERY_WARNING])
    started = dispatch(root, product_model="AN-S999", preflight_ready=True)
    check("A-starts-prepare", started.get("skill") == "product-video-prepare", str(started.get("hold")))
    case_id = started.get("case_id")
    if isinstance(case_id, str) and case_id:
        prepared = finish_prepare(root, case_id)
        check("A-advances-to-script", prepared.get("current_stage") == "SCRIPT", str(prepared.get("hold")))
    else:
        check("A-advances-to-script", False, "no case_id")

    material_root = fake_project(scratch / "material-fail")
    video = material_root / ".runtime" / "product-video-inputs" / "AN-S999_コピー" / "clip.mov"
    video.unlink()
    material = run_preflight(material_root, **start_kwargs())
    check("B-material-hold", material.get("status") == "HOLD" and material.get("hold") == HOLD_PREFLIGHT_REQUIRED)
    check("B-material-not-ready", material.get("status") != "READY")

    gemini = run_preflight(
        root,
        **start_kwargs(gemini_probe_fn=lambda: {"status": "HOLD", "hold": "HOLD_GEMINI_CLI_NOT_VERIFIED"}),
    )
    check("C-gemini-hold", gemini.get("status") == "HOLD" and gemini.get("hold") == HOLD_PREFLIGHT_REQUIRED)

    capcut = run_preflight(
        root,
        **start_kwargs(observation=ready_start_observation(capcut_tts_reachable=False)),
    )
    check("D-capcut-hold", capcut.get("status") == "HOLD" and capcut.get("hold") == HOLD_PREFLIGHT_REQUIRED)
    chatcut = run_preflight(
        root,
        **start_kwargs(observation=ready_start_observation(chatcut_connected=False)),
    )
    check("D-chatcut-hold", chatcut.get("status") == "HOLD" and chatcut.get("hold") == HOLD_PREFLIGHT_REQUIRED)

    waiting_root = fake_project(scratch / "waiting")
    case_id = "pv-AN-S999-drive-wait"
    seed_state(
        waiting_root,
        case_id,
        "WAITING_FOR_OPERATOR",
        ["PREPARE", "SCRIPT", "SCRIPT_SELECTION", "NARRATION", "ASSEMBLY", "ROUGH_EDIT"],
    )
    waiting = dispatch(waiting_root, case_id=case_id, utterance="粗編集OK", drive_fn=drive_fail)
    check("E-reaches-waiting", waiting.get("reason") == "waiting_for_operator")
    check(
        "E-drive-warning-in-existing-message",
        waiting.get("message_ja") == operator_rough_message(delivery_ready=False),
    )
    check("E-not-separate-message", waiting.get("action") == "stop" and waiting.get("status") == "OK")
    ready_wait = dispatch(waiting_root, case_id=case_id, utterance="粗編集OK", drive_fn=drive_ok)
    check("E-ready-keeps-default-message", ready_wait.get("message_ja") == OPERATOR_ROUGH_MESSAGE)

    blocked = dispatch(waiting_root, case_id=case_id, utterance=DELIVERY_APPROVAL, drive_fn=drive_fail)
    check("F-existing-drive-hold", blocked.get("hold") == "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE")
    check("F-no-export", blocked.get("export") is False)
    check("F-no-delivery-skill", blocked.get("skill") is None)
    check("F-stays-waiting", blocked.get("current_stage") == "WAITING_FOR_OPERATOR")
    state = load_state(waiting_root, case_id)
    check("F-state-not-advanced", state.get("current_stage") == "WAITING_FOR_OPERATOR")
    check("F-no-persisted-hold", state.get("hold") is None)

    recovered = prove_drive_ready(waiting_root, "AN-S999", drive_fn=drive_ok)
    check("G-drive-ready-after-login", recovered.get("status") == "OK" and recovered.get("export") is True)
    delivered = dispatch(waiting_root, case_id=case_id, utterance=DELIVERY_APPROVAL, drive_fn=drive_ok)
    check("G-delivery-after-login", delivered.get("skill") == "product-video-delivery")
    after = load_state(waiting_root, case_id)
    check("G-advances-to-delivery", after.get("current_stage") == "DELIVERY")
    complete_ok = may_complete(
        {
            "export_verified": True,
            "local_file_verified": True,
            "drive_uploaded": True,
            "drive_readback_verified": True,
        }
    )
    check("G-complete-after-readback", complete_ok.get("status") == "OK")
    src = (REPO / ".cursor" / "skills" / "product-video" / "scripts" / "delivery.py").read_text(encoding="utf-8")
    holds = set(re.findall(r"HOLD_[A-Z0-9_]+", src))
    check(
        "G-no-new-drive-hold",
        holds <= {
            "HOLD_DELIVERY_APPROVAL_REQUIRED",
            "HOLD_DELIVERY_NOT_DUE",
            "HOLD_JOB_OUTCOME_UNKNOWN",
            "HOLD_JOB_ALREADY_DONE",
            "HOLD_EXPORT_NOT_VERIFIED",
            "HOLD_DRIVE_READBACK_REQUIRED",
            "HOLD_POST_COMPLETE_PURGE_NOT_DUE",
            "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE",
            "HOLD_DRIVE_LOOKUP_TRANSIENT",
            "HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED",
            "HOLD_DRIVE_SCOPE_AMBIGUOUS",
        },
        str(holds),
    )


def main() -> int:
    print(f"REPO {REPO}")
    test_parser()
    test_approval_and_fidelity()
    test_prompt_template()
    test_script_grounding()
    test_assembly_and_variety()
    test_adjacent_visual_variety()
    test_assembly_duration_gate()
    test_telop_and_rough()
    test_caption_wrap()
    test_delivery_gates()
    test_runtime_path()
    test_git_tracked_helpers()
    test_gemini_cli_transport()
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
        test_tts_session(root)
        test_narration_queue(root)
        test_material_index_and_edit_plan(root)
        test_semantic_folder_aliases(root)
        test_visual_catalog_onboarding(root)
        test_selection_quality_case_cuts()
        test_semantic_fallback_matcher(root)
        test_minimal_range_padding()
        test_timing_metrics(root)
        test_approved_shot_history(root)
        test_create_case(root)
        test_product_facts_prepare(root)
        test_dispatch_resume(root)
        entry_root = fake_project(scratch / "initial-entry")
        test_dispatch_initial_entry(entry_root)
        held_root = fake_project(scratch / "held-resume")
        test_preflight_operator_batch(held_root)
        test_drive_deferred_preflight(scratch / "drive-deferred")
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
