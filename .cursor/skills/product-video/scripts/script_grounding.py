#!/usr/bin/env python3
"""Product-fact grounding for SCRIPT variants. No craft/quality scoring."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from constants import HOLD_SCRIPT_PRODUCT_GROUNDING
from workflow_state import hold

FACT_ID_RE = re.compile(r"^F([1-9][0-9]*)$")
HOOK_OR_CTA = frozenset({"HOOK", "CTA"})
EVIDENCE_NOTE_RE = re.compile(r"（[^）]*）|\([^)]*\)")
IDENTIFIER_LINE_RE = re.compile(
    r"(?i)(?:製品型番|商品型番|型番|JAN(?:\s*コード)?|ASIN|ISBN|EAN|SKU|商品コード)"
)
MODEL_IN_LINE_RE = re.compile(r"\bAN-[A-Z0-9]{4,8}\b")
ASIN_IN_LINE_RE = re.compile(r"\bB0[A-Z0-9]{8}\b")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
LATIN_RE = re.compile(r"[A-Za-z]{2,}")
KATAKANA_RE = re.compile(r"[ァ-ヴー]{2,}")
KANJI_RUN_RE = re.compile(r"[一-龠]{2,}")
CONTENT_KANJI = frozenset("傘骨開折")
KEY_PHRASES = (
    "uv",
    "upf",
    "チタンシルバー",
    "ルームミラー",
    "フロントガラス",
    "折りたたみ",
    "紫外線",
    "日差し",
    "10本骨",
    "本骨",
    "収納",
    "サンシェード",
    "コーティング",
    "v字",
)
CTA_FACT_RE = re.compile(r"(?i)^\s*CTA[は:：]")
QUOTED_RE = re.compile(r"「([^」]+)」")
STOPWORDS = frozenset(
    {
        "これ",
        "それ",
        "あれ",
        "この",
        "その",
        "あの",
        "ため",
        "こと",
        "もの",
        "よう",
        "する",
        "して",
        "した",
        "できる",
        "ます",
        "です",
        "ただ",
        "だけ",
        "から",
        "まで",
        "という",
        "って",
        "マジ",
        "本当",
        "本当に",
        "自分",
        "個人的",
        "今年",
        "毎日",
        "時間",
        "不満",
        "解決",
        "最高",
        "ベスト",
        "確定",
        "当たり",
        "大正解",
        "買って",
        "気に",
        "なって",
        "試して",
        "期待",
        "余裕",
        "超えて",
        "ちょっと",
        "瞬間",
        "すぐ",
        "無駄",
        "消える",
        "シンプル",
        "使い勝手",
        "完璧",
        "売り切れ",
        "急いで",
        "チェック",
        "全然",
        "違う",
        "パッと",
        "使っ",
        "使う",
        "使い",
    }
)


def _norm(text: str) -> str:
    table = str.maketrans("０１２３４５６７８９％．　", "0123456789%. ")
    return unicodedata.normalize("NFKC", text).translate(table).strip()


def split_fact_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("・").lstrip("-").strip()
        if line and line not in {"（なし）", "(なし)"}:
            lines.append(line)
    return lines


def is_identifier_fact(line: str) -> bool:
    compact = _norm(line)
    if IDENTIFIER_LINE_RE.search(compact):
        return True
    if MODEL_IN_LINE_RE.fullmatch(compact):
        return True
    if ASIN_IN_LINE_RE.fullmatch(compact):
        return True
    if re.fullmatch(r"\d{8,14}", compact):
        return True
    return False


def build_fact_catalog(product_information: str, product_appeal_points: str = "") -> dict[str, Any]:
    facts: list[dict[str, str]] = []
    seen: set[str] = set()
    next_id = 1
    for source, block in (
        ("information", product_information),
        ("appeal", product_appeal_points),
    ):
        for line in split_fact_lines(block):
            if is_identifier_fact(line):
                continue
            key = _norm(line)
            if key in seen:
                continue
            seen.add(key)
            facts.append({"id": f"F{next_id}", "text": line, "source": source})
            next_id += 1
    by_id = {item["id"]: item for item in facts}
    return {"status": "OK", "facts": facts, "by_id": by_id}


def identifier_lines(*blocks: str) -> list[str]:
    return [line for block in blocks for line in split_fact_lines(block) if is_identifier_fact(line)]


def label_product_blocks(product_information: str, product_appeal_points: str = "") -> dict[str, Any]:
    catalog = build_fact_catalog(product_information, product_appeal_points)
    info_facts = [item for item in catalog["facts"] if item["source"] == "information"]
    appeal_facts = [item for item in catalog["facts"] if item["source"] == "appeal"]
    info_ids = identifier_lines(product_information)
    appeal_ids = identifier_lines(product_appeal_points)

    def format_block(items: list[dict[str, str]], extras: list[str], empty: str) -> str:
        parts = [f"{item['id']}: {item['text']}" for item in items]
        if extras:
            parts.append("（セリフに入れない識別情報）")
            parts.extend(extras)
        return "\n".join(parts) if parts else empty

    return {
        "status": "OK",
        "facts": catalog["facts"],
        "by_id": catalog["by_id"],
        "product_information": format_block(info_facts, info_ids, "（なし）"),
        "product_appeal_points": format_block(appeal_facts, appeal_ids, "（なし）"),
    }


def parse_evidence_ids(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    for part in str(raw).replace("、", ",").split(","):
        token = EVIDENCE_NOTE_RE.sub("", part).strip().upper()
        if not token:
            return []
        if token.startswith("F") and token[1:].isdigit():
            token = f"F{int(token[1:])}"
        elif token in HOOK_OR_CTA:
            token = token
        else:
            return []
        if token not in seen:
            seen.add(token)
            found.append(token)
    return found


def is_cta_fact(line: str) -> bool:
    return bool(CTA_FACT_RE.search((line or "").strip()))


def product_facts(catalog: dict[str, Any]) -> list[dict[str, str]]:
    return [item for item in catalog.get("facts") or [] if not is_cta_fact(item.get("text") or "")]


def _is_number(token: str) -> bool:
    return bool(NUMBER_RE.fullmatch(token))


def distinctive_markers(text: str) -> set[str]:
    compact = _norm(text)
    markers: set[str] = set()
    for match in LATIN_RE.findall(compact):
        token = match.lower()
        if token not in STOPWORDS:
            markers.add(token)
    for match in NUMBER_RE.findall(compact):
        markers.add(match)
    for match in KATAKANA_RE.findall(compact):
        if match not in STOPWORDS:
            markers.add(match)
    for match in KANJI_RUN_RE.findall(compact):
        if match not in STOPWORDS:
            markers.add(match)
    for kanji in CONTENT_KANJI:
        if kanji in compact:
            markers.add(kanji)
    folded = compact.lower()
    for phrase in KEY_PHRASES:
        if phrase in folded or phrase in compact:
            markers.add(phrase)
    return markers


def significant_tokens(text: str) -> set[str]:
    return distinctive_markers(text)


def markers_overlap(fact_markers: set[str], line_markers: set[str]) -> bool:
    for left in fact_markers:
        for right in line_markers:
            if left == right:
                return True
            if _is_number(left) or _is_number(right):
                continue
            if len(left) >= 2 and len(right) >= 2 and (left in right or right in left):
                return True
    return False


def line_matches_fact(line: str, fact_text: str) -> bool:
    spoken = _norm(line)
    fact = _norm(fact_text)
    if not spoken or not fact:
        return False
    for quoted in QUOTED_RE.findall(fact_text):
        if _norm(quoted) and _norm(quoted) in spoken:
            return True
    if len(fact) >= 4 and fact in spoken:
        return True
    if len(spoken) >= 4 and spoken in fact:
        return True
    return markers_overlap(distinctive_markers(fact_text), distinctive_markers(line))


def actual_facts_for_line(line: str, catalog: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for item in product_facts(catalog):
        if line_matches_fact(line, item["text"]):
            found.append(item["id"])
    return found


def numbers_in(text: str) -> set[str]:
    return set(NUMBER_RE.findall(_norm(text)))


def variant_for_operator(variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant_id": variant.get("variant_id"),
        "title": variant.get("title"),
        "estimated_seconds": variant.get("estimated_seconds"),
        "cuts": [
            {
                "cut_id": cut.get("cut_id"),
                "index": cut.get("index"),
                "situation": cut.get("situation"),
                "line": cut.get("line"),
                "telop_only": cut.get("telop_only") is True,
            }
            for cut in variant.get("cuts") or []
        ],
    }


def present_for_operator(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "OK",
        "variant_count": parsed.get("variant_count"),
        "variants": [variant_for_operator(item) for item in parsed.get("variants") or []],
    }


def prove_variant_grounding(
    variant: dict[str, Any],
    catalog: dict[str, Any],
    *,
    product_information: str,
    product_appeal_points: str = "",
) -> dict[str, Any]:
    by_id: dict[str, Any] = catalog.get("by_id") or {}
    allowed_facts = set(by_id)
    if len(product_facts(catalog)) < 3:
        return hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            "fewer than 3 product facts after excluding identifiers",
            regenerate=False,
            variant_id=variant.get("variant_id"),
        )
    allowed_numbers = numbers_in(product_information) | numbers_in(product_appeal_points)
    cuts = list(variant.get("cuts") or [])
    used: set[str] = set()
    mismatches: list[dict[str, Any]] = []
    reasons: list[str] = []
    for index, cut in enumerate(cuts):
        ids = [str(item) for item in (cut.get("evidence_ids") or [])]
        line = str(cut.get("line") or "")
        role = {item for item in ids if item in HOOK_OR_CTA}
        assigned = [item for item in ids if item not in HOOK_OR_CTA]
        if not ids:
            reasons.append(f"cut {cut.get('index')} missing 根拠ID")
        elif role and assigned:
            reasons.append(f"cut {cut.get('index')} mixed HOOK/CTA with F-IDs")
        elif len(role) > 1:
            reasons.append(f"cut {cut.get('index')} has both HOOK and CTA")
        for fact_id in assigned:
            if fact_id not in allowed_facts:
                reasons.append(f"cut {cut.get('index')} unknown {fact_id}")
        actual = actual_facts_for_line(line, catalog)
        cut["actual_fact_ids"] = actual
        assigned_known = [item for item in assigned if item in allowed_facts]
        mismatch = bool(assigned_known) and set(assigned_known) != set(actual)
        cut["evidence_id_mismatch"] = mismatch
        if mismatch:
            mismatches.append(
                {
                    "cut_id": cut.get("cut_id"),
                    "evidence_ids": assigned_known,
                    "actual_fact_ids": actual,
                }
            )
        used.update(actual)
        invented = numbers_in(line) - allowed_numbers
        if invented:
            reasons.append(f"cut {cut.get('index')} invented number {sorted(invented)}")
        if MODEL_IN_LINE_RE.search(_norm(line)) or ASIN_IN_LINE_RE.search(_norm(line)):
            reasons.append(f"cut {cut.get('index')} contains a product identifier")
    first_three = cuts[:3]
    early_fact = any(bool(cut.get("actual_fact_ids")) for cut in first_three)
    if not early_fact:
        reasons.append("no product fact in the first 3 cuts")
    if len(used) < 3:
        reasons.append(f"used {len(used)} distinct product facts, need 3")
    if not used:
        reasons.append("script is HOOK/generic only")
    if reasons:
        return hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            "; ".join(reasons),
            regenerate=True,
            variant_id=variant.get("variant_id"),
            actual_used_fact_ids=sorted(used, key=lambda item: int(item[1:]) if item[1:].isdigit() else 0),
            evidence_id_mismatch=mismatches,
        )
    return {
        "status": "OK",
        "actual_used_fact_ids": sorted(used, key=lambda item: int(item[1:])),
        "used_fact_ids": sorted(used, key=lambda item: int(item[1:])),
        "evidence_id_mismatch": mismatches,
    }


def prove_scripts_grounding(
    parsed: dict[str, Any],
    product_information: str,
    product_appeal_points: str = "",
) -> dict[str, Any]:
    catalog = build_fact_catalog(product_information, product_appeal_points)
    usable = product_facts(catalog)
    if len(usable) < 3:
        return hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            "fewer than 3 product facts after excluding identifiers",
            regenerate=False,
            fact_count=len(usable),
        )
    failures: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for variant in parsed.get("variants") or []:
        proof = prove_variant_grounding(
            variant,
            catalog,
            product_information=product_information,
            product_appeal_points=product_appeal_points,
        )
        if proof.get("status") != "OK":
            failures.append(proof)
            continue
        if proof.get("evidence_id_mismatch"):
            mismatches.append(
                {
                    "variant_id": variant.get("variant_id"),
                    "mismatches": proof["evidence_id_mismatch"],
                }
            )
    if failures:
        return hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            failures[0].get("reason") or "script product grounding failed",
            regenerate=True,
            failed_variant_count=len(failures),
            failures=[{"variant_id": item.get("variant_id"), "reason": item.get("reason")} for item in failures],
        )
    return {
        "status": "OK",
        "fact_ids": [item["id"] for item in catalog["facts"]],
        "presentation": present_for_operator(parsed),
        "evidence_id_mismatch": mismatches,
    }


BASE_FORBIDDEN_LINE_SUBSTRINGS = ("慶洋エンジニアリング",)
BASE_POLITE_RE = re.compile(r"です(?!ぐ)|ます|でした|でしょう|ません|ましょう")


def _line_has_exclamation(text: str) -> bool:
    return "！" in text or "!" in text


def base_script_line_issues(variants: list[dict[str, Any]]) -> list[str]:
    """Spoken-line bans that apply to every product."""
    issues: list[str] = []
    for variant in variants:
        variant_id = variant.get("variant_id")
        title = str(variant.get("title") or "")
        cuts = variant.get("cuts") or []
        spoken = [(-1, title)] + [(index, str(cut.get("line") or "")) for index, cut in enumerate(cuts)]
        for index, text in spoken:
            where = f"variant {variant_id} title" if index < 0 else f"variant {variant_id} cut {index + 1} line"
            for token in BASE_FORBIDDEN_LINE_SUBSTRINGS:
                if token in text:
                    issues.append(f"{where} contains {token}")
            if text.strip() and BASE_POLITE_RE.search(_norm_rule_text(text)):
                issues.append(f"{where} uses polite speech")
        marks = [_line_has_exclamation(str(cut.get("line") or "")) for cut in cuts]
        if len(marks) >= 2 and all(marks):
            issues.append(f"variant {variant_id} puts an exclamation on every line")
    return issues


def load_product_script_rule_profile(project_root: Path, product_model: str) -> dict[str, Any]:
    if not product_model:
        return {}
    path = project_root / "config" / f"product_video_script_rules_{product_model}.v1.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("product_model") != product_model:
        raise ValueError(f"script rules product_model mismatch: {path.name}")
    return data


def _norm_rule_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace(" ", "").replace("\u3000", "")


def product_script_rule_issues(
    project_root: Path,
    product_model: str,
    variants: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
) -> list[str]:
    """Spoken-line bans for one product. Empty when that product has no rules file."""
    loaded = load_product_script_rule_profile(project_root, product_model) if profile is None else profile
    if not loaded:
        return []
    forbidden = [_norm_rule_text(str(item)) for item in loaded.get("forbidden_line_substrings") or [] if str(item).strip()]
    forbidden_regex = [re.compile(str(item)) for item in loaded.get("forbidden_line_regex") or [] if str(item).strip()]
    if "forbidden_situation_substrings" in loaded:
        situation_forbidden = [
            _norm_rule_text(str(item))
            for item in loaded.get("forbidden_situation_substrings") or []
            if str(item).strip()
        ]
    else:
        situation_forbidden = forbidden
    late_tokens = [_norm_rule_text(str(item)) for item in loaded.get("late_detail_substrings") or [] if str(item).strip()]
    required_groups: list[list[str]] = []
    for group in loaded.get("required_any_substrings") or []:
        if isinstance(group, str):
            group = [group]
        options = [_norm_rule_text(str(item)) for item in group if str(item).strip()]
        if options:
            required_groups.append(options)
    fraction = float(loaded.get("late_detail_after_fraction") or 0.5)
    exclamation_suffix = str(loaded.get("exclamation_only_suffix") or "")
    telop_only_lines = [str(item).strip() for item in loaded.get("telop_only_lines") or [] if str(item).strip()]
    issues: list[str] = []
    for variant in variants:
        variant_id = variant.get("variant_id")
        cuts = variant.get("cuts") or []
        late_start = int(len(cuts) * fraction)
        chunks: list[tuple[int, str, str]] = []
        title = str(variant.get("title") or "")
        if title.strip():
            chunks.append((-1, "title", title))
        for index, cut in enumerate(cuts):
            chunks.append((index, "situation", str(cut.get("situation") or "")))
            chunks.append((index, "line", str(cut.get("line") or "")))
        spoken_parts = [title]
        for index, field, text in chunks:
            normalized = _norm_rule_text(text)
            if field in {"title", "line"} and text.strip():
                spoken_parts.append(text)
            if not normalized:
                continue
            where = f"variant {variant_id} {field}" if index < 0 else f"variant {variant_id} cut {index + 1} {field}"
            active = forbidden if field in {"title", "line"} else situation_forbidden
            for token in active:
                if token in normalized:
                    issues.append(f"{where} speaks forbidden spec: {token}")
            if field in {"title", "line"}:
                for pattern in forbidden_regex:
                    if pattern.search(normalized):
                        issues.append(f"{where} speaks forbidden spec: {pattern.pattern}")
            if index < late_start:
                for token in late_tokens:
                    if token in normalized:
                        issues.append(f"{where} speaks detail too early: {token}")
            if exclamation_suffix and field == "line":
                marks = text.count("！") + text.count("!")
                is_last = index == len(cuts) - 1
                allowed = exclamation_suffix.count("！") + exclamation_suffix.count("!")
                if is_last and text.endswith(exclamation_suffix):
                    if marks != allowed:
                        issues.append(f"{where} has an exclamation outside {exclamation_suffix}")
                elif marks:
                    issues.append(f"{where} has an exclamation outside the final CTA")
            if exclamation_suffix and field == "title" and ("！" in text or "!" in text):
                issues.append(f"{where} has an exclamation outside the final CTA")
            if field == "line" and "かける" in forbidden and "1136" in normalized and "×" not in text:
                issues.append(f"{where} must write 1136×640")
            if field == "line" and telop_only_lines and ("アプリ" in text or text.strip() in telop_only_lines):
                cut = cuts[index]
                if text.strip() not in telop_only_lines or cut.get("telop_only") is not True:
                    issues.append(f"{where} must be telop-only: {telop_only_lines[0]}")
        spoken = _norm_rule_text("\n".join(spoken_parts))
        for options in required_groups:
            if not any(token in spoken for token in options):
                issues.append(f"variant {variant_id} missing required: {' / '.join(options)}")
        lines = [_norm_rule_text(str(cut.get("line") or "")) for cut in cuts]
        for pair in loaded.get("must_precede") or []:
            if not isinstance(pair, dict):
                continue
            before = _norm_rule_text(str(pair.get("before") or ""))
            after = _norm_rule_text(str(pair.get("after") or ""))
            if not before or not after:
                continue
            before_at = next((i for i, line in enumerate(lines) if before in line), None)
            after_at = next((i for i, line in enumerate(lines) if after in line), None)
            if pair.get("same_line") is True:
                named = lines[after_at] if after_at is not None else ""
                if after_at is None or before not in named or named.find(before) > named.find(after):
                    issues.append(f"variant {variant_id} needs {pair.get('before')} before {pair.get('after')} in the same cut")
                elif after_at == 0:
                    issues.append(f"variant {variant_id} must not open on {pair.get('after')}")
                if any(before in line and after not in line for line in lines):
                    issues.append(f"variant {variant_id} splits {pair.get('before')} into its own cut")
            elif before_at is None or after_at is None or before_at >= after_at:
                issues.append(f"variant {variant_id} needs {pair.get('before')} before {pair.get('after')}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--present", type=argparse.FileType("r", encoding="utf-8"))
    parser.add_argument("--product-information", default="")
    parser.add_argument("--appeal-points", default="")
    parser.add_argument("--variants-json", type=argparse.FileType("r", encoding="utf-8"))
    args = parser.parse_args()
    if args.present:
        parsed = json.load(args.present)
        print(json.dumps(present_for_operator(parsed), ensure_ascii=False, indent=2))
        return 0
    if args.variants_json:
        parsed = json.load(args.variants_json)
        payload = prove_scripts_grounding(parsed, args.product_information, args.appeal_points)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("status") == "OK" else 2
    labeled = label_product_blocks(args.product_information, args.appeal_points)
    print(json.dumps(labeled, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
