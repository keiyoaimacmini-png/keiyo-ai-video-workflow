#!/usr/bin/env python3
"""Load per-model verified product facts for PREPARE. Not a settings file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from constants import HOLD_PRODUCT_FACTS_REQUIRED, MIN_USABLE_PRODUCT_FACTS
from paths import emit, project_root_from
from script_grounding import build_fact_catalog
from workflow_state import hold

FACTS_NAME = "product_video_product_facts_{model}.v1.json"
CTA_FACT_RE = re.compile(r"(?i)^\s*CTA[は:：]")


def facts_path_for(project_root: Path, product_model: str) -> Path:
    return project_root / "config" / FACTS_NAME.format(model=product_model)


def is_cta_fact(line: str) -> bool:
    return bool(CTA_FACT_RE.search((line or "").strip()))


def usable_product_facts(product_information: str, product_appeal_points: str = "") -> list[dict[str, str]]:
    catalog = build_fact_catalog(product_information, product_appeal_points)
    return [item for item in catalog["facts"] if not is_cta_fact(item["text"])]


def lines_to_block(values: list[str]) -> str:
    return "\n".join(f"- {line}" for line in values if str(line).strip())


def prove_usable_product_facts(
    product_information: str,
    product_appeal_points: str = "",
    *,
    product_model: str,
    facts_path: Path | str,
) -> dict[str, Any]:
    usable = usable_product_facts(product_information, product_appeal_points)
    count = len(usable)
    path = Path(facts_path).as_posix()
    if count < MIN_USABLE_PRODUCT_FACTS:
        return hold(
            HOLD_PRODUCT_FACTS_REQUIRED,
            "need at least 3 grounding facts excluding identifiers and CTA",
            product_model=product_model,
            usable_fact_count=count,
            expected_facts_profile_path=path,
        )
    return {
        "status": "OK",
        "product_model": product_model,
        "usable_fact_count": count,
        "expected_facts_profile_path": path,
        "usable_facts": [item["text"] for item in usable],
    }


def load_product_facts_profile(project_root: Path, product_model: str) -> dict[str, Any]:
    root = project_root_from(project_root)
    path = facts_path_for(root, product_model)
    if path.is_symlink() or not path.is_file():
        return hold(
            HOLD_PRODUCT_FACTS_REQUIRED,
            "product facts profile is missing; register it once for this model",
            product_model=product_model,
            usable_fact_count=0,
            expected_facts_profile_path=path.as_posix(),
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return hold(
            HOLD_PRODUCT_FACTS_REQUIRED,
            "product facts profile is unreadable",
            product_model=product_model,
            usable_fact_count=0,
            expected_facts_profile_path=path.as_posix(),
        )
    if not isinstance(data, dict) or data.get("product_model") != product_model:
        return hold(
            HOLD_PRODUCT_FACTS_REQUIRED,
            "product facts profile product_model must equal the requested model",
            product_model=product_model,
            usable_fact_count=0,
            expected_facts_profile_path=path.as_posix(),
        )
    raw_facts = [item.strip() for item in (data.get("verified_facts") or []) if isinstance(item, str) and item.strip()]
    raw_appeals = [item.strip() for item in (data.get("appeal_points") or []) if isinstance(item, str) and item.strip()]
    proof = prove_usable_product_facts(
        lines_to_block(raw_facts),
        lines_to_block(raw_appeals),
        product_model=product_model,
        facts_path=path,
    )
    if proof.get("status") != "OK":
        return proof
    return {
        "status": "OK",
        "product_model": product_model,
        "facts_path": path.as_posix(),
        "verified_facts": raw_facts,
        "appeal_points": raw_appeals,
        "usable_fact_count": proof["usable_fact_count"],
        "expected_facts_profile_path": path.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--product-model", required=True)
    args = parser.parse_args()
    payload = load_product_facts_profile(args.project_root, args.product_model)
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
