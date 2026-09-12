#!/usr/bin/env python3
"""Product-fact grounding for SCRIPT variants. No craft/quality scoring."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from typing import Any

from constants import HOLD_SCRIPT_PRODUCT_GROUNDING
from workflow_state import hold

FACT_ID_RE = re.compile(r"^F([1-9][0-9]*)$")
HOOK_OR_CTA = frozenset({"HOOK", "CTA"})
IDENTIFIER_LINE_RE = re.compile(
    r"(?i)(?:製品型番|商品型番|型番|JAN(?:\s*コード)?|ASIN|ISBN|EAN|SKU|商品コード)"
)
MODEL_IN_LINE_RE = re.compile(r"\bAN-[A-Z0-9]{4,6}\b")
ASIN_IN_LINE_RE = re.compile(r"\bB0[A-Z0-9]{8}\b")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
TOKEN_RE = re.compile(r"[A-Za-z]{3,}|[0-9]+(?:\.\d+)?|[一-龠]{2,}|[ァ-ヴー]{2,}|[ぁ-ん]{3,}")
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
        token = part.strip().upper()
        if token.startswith("F") and token[1:].isdigit():
            token = f"F{int(token[1:])}"
        elif token in HOOK_OR_CTA:
            token = token
        else:
            continue
        if token not in seen:
            seen.add(token)
            found.append(token)
    leftover = str(raw).replace("、", ",")
    for part in leftover.split(","):
        token = part.strip()
        if not token:
            continue
        folded = token.upper()
        if folded in HOOK_OR_CTA or FACT_ID_RE.fullmatch(folded):
            continue
        return []
    return found


def significant_tokens(text: str) -> set[str]:
    tokens = set()
    for match in TOKEN_RE.findall(_norm(text)):
        if match in STOPWORDS:
            continue
        if match.isdigit() and len(match) == 1:
            continue
        tokens.add(match)
    return tokens


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
    fact_tokens = significant_tokens(fact_text)
    line_tokens = significant_tokens(line)
    if fact_tokens and line_tokens & fact_tokens:
        return True
    return False


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
    if len(allowed_facts) < 3:
        return hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            "fewer than 3 product facts after excluding identifiers",
            regenerate=False,
            variant_id=variant.get("variant_id"),
        )
    allowed_numbers = numbers_in(product_information) | numbers_in(product_appeal_points)
    cuts = list(variant.get("cuts") or [])
    used: set[str] = set()
    generic_only = True
    reasons: list[str] = []
    for index, cut in enumerate(cuts):
        ids = [str(item) for item in (cut.get("evidence_ids") or [])]
        line = str(cut.get("line") or "")
        role = {item for item in ids if item in HOOK_OR_CTA}
        facts = [item for item in ids if item not in HOOK_OR_CTA]
        if not ids:
            reasons.append(f"cut {cut.get('index')} missing 根拠ID")
            continue
        if role and facts:
            reasons.append(f"cut {cut.get('index')} mixed HOOK/CTA with F-IDs")
            continue
        if len(role) > 1:
            reasons.append(f"cut {cut.get('index')} has both HOOK and CTA")
            continue
        if role:
            continue
        if not facts:
            reasons.append(f"cut {cut.get('index')} has no F-ID")
            continue
        for fact_id in facts:
            if fact_id not in allowed_facts:
                reasons.append(f"cut {cut.get('index')} unknown {fact_id}")
                continue
            if line_matches_fact(line, by_id[fact_id]["text"]):
                used.add(fact_id)
                generic_only = False
            else:
                reasons.append(f"cut {cut.get('index')} line unrelated to {fact_id}")
        invented = numbers_in(line) - allowed_numbers
        if invented:
            reasons.append(f"cut {cut.get('index')} invented number {sorted(invented)}")
        if MODEL_IN_LINE_RE.search(_norm(line)) or ASIN_IN_LINE_RE.search(_norm(line)):
            reasons.append(f"cut {cut.get('index')} contains a product identifier")
        if index < 3 and facts:
            generic_only = False
    first_three = cuts[:3]
    early_fact = any(
        any(item not in HOOK_OR_CTA for item in (cut.get("evidence_ids") or []))
        for cut in first_three
    )
    if not early_fact:
        reasons.append("no F-ID in the first 3 cuts")
    if len(used) < 3:
        reasons.append(f"used {len(used)} distinct F-IDs, need 3")
    if generic_only or not used:
        reasons.append("script is HOOK/generic only")
    if reasons:
        return hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            "; ".join(reasons),
            regenerate=True,
            variant_id=variant.get("variant_id"),
            used_fact_ids=sorted(used, key=lambda item: int(item[1:]) if item[1:].isdigit() else 0),
        )
    return {"status": "OK", "used_fact_ids": sorted(used, key=lambda item: int(item[1:]))}


def prove_scripts_grounding(
    parsed: dict[str, Any],
    product_information: str,
    product_appeal_points: str = "",
) -> dict[str, Any]:
    catalog = build_fact_catalog(product_information, product_appeal_points)
    if len(catalog["facts"]) < 3:
        return hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            "fewer than 3 product facts after excluding identifiers",
            regenerate=False,
            fact_count=len(catalog["facts"]),
        )
    failures: list[dict[str, Any]] = []
    for variant in parsed.get("variants") or []:
        proof = prove_variant_grounding(
            variant,
            catalog,
            product_information=product_information,
            product_appeal_points=product_appeal_points,
        )
        if proof.get("status") != "OK":
            failures.append(proof)
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
    }


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
