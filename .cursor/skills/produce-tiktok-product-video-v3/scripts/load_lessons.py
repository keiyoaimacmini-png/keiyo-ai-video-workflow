#!/usr/bin/env python3
"""Load active product-video v3 lessons."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lessons import SURFACES, dump, load_active_lessons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--surface", choices=SURFACES)
    parser.add_argument("--product-model")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        from record_lesson import self_test as record_self_test

        return record_self_test()
    if args.project_root is None:
        parser.error("--project-root is required unless --self-test is used")
    try:
        lessons = load_active_lessons(args.project_root.resolve(), args.surface, args.product_model)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(dump(lessons), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
