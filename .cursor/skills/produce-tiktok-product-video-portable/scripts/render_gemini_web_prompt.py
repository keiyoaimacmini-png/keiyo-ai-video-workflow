#!/usr/bin/env python3
"""Render a key-free Gemini prompt from a local brief.

No network. No API keys. The host sends the printed text into official
Gemini.app on this Mac, in a 一時チャット at Gemini 3.8 Flash, after
verified facts exist. Do not leave a paste for the operator.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


BRIEF_SCHEMA = "product_video_gemini_web_brief.v1"
CTA_TEXT = "下からチェック！"
NARRATIVE_ROLES = (
    "problem_or_hook",
    "product",
    "use_or_change",
    "result",
    "problem_resolution",
    "cta",
)
SECRET_RE = re.compile(r"(?i)(?:x-goog-api-key\s*[:=]\s*)[^\s\"']+|AIza[0-9A-Za-z_\-]{10,}")
FORBIDDEN_KEY_RE = re.compile(
    r"(?i)(sha256|in_sec|out_sec|source_in|source_out|cookie|token|api[_-]?key|password)"
)


def hold(code: str, reason: str) -> dict[str, str]:
    return {"status": "HOLD", "hold": code, "reason": reason}


def load_brief(text: str) -> dict[str, Any]:
    if SECRET_RE.search(text):
        raise ValueError("brief must not contain secrets")
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("schema") != BRIEF_SCHEMA:
        raise ValueError("brief schema mismatch")
    facts = data.get("verified_facts")
    shots = data.get("usable_shots")
    if not isinstance(facts, list) or not facts:
        raise ValueError("verified_facts required")
    if data.get("cta_text") != CTA_TEXT:
        raise ValueError("cta_text must be the frozen CTA")
    blob = json.dumps(data, ensure_ascii=False)
    if FORBIDDEN_KEY_RE.search(blob):
        raise ValueError("brief must not include hashes, in/out, cookies, tokens, or keys")
    for fact in facts:
        if not isinstance(fact, str) or not fact.strip():
            raise ValueError("verified_facts must be non-empty strings")
        if re.search(r"AN-[A-Z0-9]{4,6}", fact):
            raise ValueError("verified_facts must not include product-model codes")
    if shots is None:
        return data
    if not isinstance(shots, list):
        raise ValueError("usable_shots must be a list when present")
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("usable_shots must be objects")
        action = shot.get("observed_action")
        asset_id = shot.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("usable_shots need asset_id")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("usable_shots need observed_action")
        if re.search(r"AN-[A-Z0-9]{4,6}", action):
            raise ValueError("observed_action must not include product-model codes")
        extra = set(shot) - {"asset_id", "observed_action"}
        if extra:
            raise ValueError("usable_shots may only include asset_id and observed_action")
    return data


def format_verified_facts(facts: list[Any]) -> str:
    lines: list[str] = []
    for fact in facts:
        text = str(fact).strip()
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines)


def render_prompt(brief: dict[str, Any]) -> str:
    product_model = brief.get("product_model")
    if not isinstance(product_model, str) or not product_model.strip():
        raise ValueError("product_model required")
    facts = format_verified_facts(brief.get("verified_facts") or [])
    if not facts:
        raise ValueError("verified_facts required")
    return f"""あなたはTikTok向けの短尺商品動画の台本担当。

【目的】

露骨な売り込みを避け、視聴維持・コメント・保存・シェア・自然な購買につながる可能性を狙う。
作成するのは、台詞と想定映像を含む台本ドラフト1案だけ。

【前提と入力】

素材の事前確認を前提にしない。
確認済みの商品情報から台詞を作り、必要な映像を企画として提案する。
既存素材の内容・有無は判断しない。

内部の製品型番: {product_model}

verified_facts:
確認済みの商品情報。
特徴・機能・使い方・使用による変化など、確認できた事項だけを記載する。
少なくとも1つの使い方と、困りごとの解決を裏づける情報を含める。

{facts}

【作業範囲】

- 商品ページの再取得、追加質問はしない。
- 動画素材の検索・取得・分析・選定はしない。
- 編集タイムライン、カット表、編集指示、SE/BGM、投稿文、採点は作らない。
- 既存ファイルの指名や、素材の識別情報は出さない。
  識別情報には、ファイル名、asset_id、ハッシュ、開始終了秒を含む。
- 型番は内部参照のみ。出力には書かず、画面・音声への表示も前提にしない。
- 指定形式以外の説明、前置き、別案は出さない。

【企画の選定】

- 切り口を内部で20案比較し、実行可能な1案だけを選ぶ。
- 確認済みの商品情報で、冒頭の困りごとから解決まで成立する案を選ぶ。
- 情報が足りない場合は、入力で解決まで言える範囲に困りごとを狭める。
- 比較過程や不採用案は出力せず、ユーザーに選ばせない。

【事実と提案の区別】

- 台詞で述べる商品の特徴・機能・使い方・変化・解決は、verified_facts に根拠がある内容だけにする。
- 未確認の効能・数値・他社比較・実演結果・体験談・使用者の感情は作らない。
- バズや売上を保証しない。
- 狙う感情は selected_concept に企画意図として書く。実際に起きる反応として断定しない。
- 想定映像は企画上の提案とする。ただし、未確認の機能や効果を示す映像は提案しない。
- 既存動画の文言はコピーしない。

【台詞の条件】

- 以下の6段を順番どおりに書く。省略・逆順は禁止。
- 各段の台詞は1行。耳で聞いて分かる短い話し言葉にする。
- 6行を独立したキャプションにせず、隣の行と自然につながる一続きの話にする。
- ドパガキに刺さるセリフにする。TikTokを見ている若い層に、友達に話しかける短い口語。
- 非CTAは一息で言い切る。前置き、長い修飾、手順の実況は削る。目安は20字前後。24字を超えない。
- 冒頭2秒で止まる理由を作り、説明から入らない。
- テンポを優先し、広告調、取説調、丁寧すぎる実況、紹介文を避ける。
- 「〜します」「してみて」「あるよ」「役立つのが」は使わない。
- 商品は「そんな時はこれ」程度で出し、いきなりスペックを列挙しない。
- 使い方は動作を一言。結果は理由を短く。解決は困りごとを一言で閉じる。
- 次を聞きたくなる情報の出し方にする。
- コメントや保存につながる余地を残す。ただし、直接コメントを求めない。
- 非CTAの大半を「〜よ」「だよ」で終わらせず、語尾を揃えない。
- 台詞本文に画の指定を書かない。

【6段の役割】

1. problem_or_hook
視聴者の困りごとで止める。
後段の確認済み事実で解決できる困りごとにする。

2. product
呼び名、商品カテゴリ名、「これ」などで、フックから商品へ自然につなぐ。

3. use_or_change
商品の使い方を短く言う。
ぼかさず、確認済みの具体的な動作を言う。

4. result
使用によって起きる、確認済みの変化を言う。
「〜から」など、次の解決につながる理由として伝える。

5. problem_resolution
冒頭と同じ困りごとの解決を言う。
result の言い換えで終わらせない。
見た目や部分的な変化だけで、困りごと全体を解決したことにしない。

6. cta
台詞は「下からチェック！」と完全一致。

【想定映像】

各段に picture_must と picture_ideal を付ける。
どちらも、これから用意する映像の要件・提案であり、確認済み素材の説明ではない。

picture_must:
- その台詞を成立させるために、画面で見せる必要がある動作を1つ書く。
- 台詞の言い直しではなく、具体的な動作を書く。
- CTAは、商品または直前の使用結果を見せる動作でよい。
- 同じ動作を複数の段に使ってよい。

picture_ideal:
- 距離「寄り／中／引き」と、カメラ「固定／手持ち／パン」から各1語を選ぶ。
- 「寄り 固定」のように、空白で区切った2語だけを書く。
- 隣接する段で、同じ組み合わせを連続させない。
- 表情、秒数、特殊アングル、照明は書かない。

picture_must は内容上の必須条件。
picture_ideal は見せ方の希望であり、実際のカット切り替えを確定するものではない。

【出力形式】

selected_concept:
選んだ切り口、狙う感情、採用理由を短い1文で書く。

dialogue:
6件。各要素は次の5項目だけ。

cut_id
narrative_role
text
picture_must
picture_ideal

cut_id は1〜6の段番号であり、編集カット番号ではない。
narrative_role は【6段の役割】に指定した名称を使う。
"""


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    good = {
        "schema": BRIEF_SCHEMA,
        "product_model": "AN-S182",
        "cta_text": CTA_TEXT,
        "verified_facts": ["仮眠が続かない"],
    }
    prompt = render_prompt(good)
    check("cta-in-prompt", CTA_TEXT in prompt)
    check("six-roles", all(role in prompt for role in NARRATIVE_ROLES))
    check("spoken-tiktok", "ドパガキに刺さるセリフ" in prompt)
    check("talk-to-young-viewers", "友達に話しかける短い口語" in prompt)
    check("short-breath", "一息で言い切る" in prompt)
    check("short-char-cap", "24字を超えない" in prompt)
    check("one-beat-use", "使い方は動作を一言" in prompt)
    check("first-two-seconds", "冒頭2秒で止まる理由を作り" in prompt)
    check("not-hard-sell", "露骨な売り込みを避け" in prompt)
    check("vary-yo-endings", "非CTAの大半を「〜よ」「だよ」で終わらせず" in prompt)
    check("no-inventory", "素材の事前確認を前提にしない" in prompt)
    check("no-product-examples", all(token not in prompt for token in ("傘型", "日差し", "車種")))
    check("kasa-mitai-not-banned", "傘みたいに" not in prompt)
    check("closes-hook", "冒頭と同じ困りごとの解決を言う" in prompt)
    check("not-looks-only", "result の言い換えで終わらせない" in prompt)
    check("hook-not-looks-only", "見た目や部分的な変化だけで、困りごと全体を解決したことにしない" in prompt)
    check("no-procedure", "取説調" in prompt)
    check("no-ask", "ユーザーに選ばせない" in prompt)
    check("no-question-stop", "追加質問はしない" in prompt)
    check("picture-must", "picture_must" in prompt)
    check("picture-ideal", "picture_ideal" in prompt)
    check("ideal-shot-grammar", "寄り／中／引き" in prompt)
    check("no-observed-actions", "observed_actions" not in prompt)
    check("no-twenty-summary", "twenty_candidate_summary" not in prompt)
    check("facts-in-prompt", "- 仮眠が続かない" in prompt)
    check("no-asset-id-value", "asset-a" not in prompt)
    check("no-secret", "AIza" not in prompt)
    with_shots = {
        **good,
        "usable_shots": [{"asset_id": "asset-a", "observed_action": "shade opens"}],
    }
    check("shots-not-in-prompt", "shade opens" not in render_prompt(with_shots))
    try:
        load_brief(json.dumps(good))
        check("facts-only-brief", True)
    except ValueError:
        check("facts-only-brief", False)
    try:
        load_brief(json.dumps({**good, "usable_shots": [{"asset_id": "a", "observed_action": "x", "sha256": "abc"}]}))
        check("reject-sha", False)
    except ValueError:
        check("reject-sha", True)
    try:
        load_brief('{"schema":"nope"}')
        check("reject-schema", False)
    except ValueError:
        check("reject-schema", True)
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: render_gemini_web_prompt", flush=True)
        return 1
    print("SELF-TEST PASSED: render_gemini_web_prompt")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=argparse.FileType("r", encoding="utf-8"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.brief is None:
        parser.error("--brief is required unless --self-test is used")
    try:
        brief = load_brief(args.brief.read())
        prompt = render_prompt(brief)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = hold("HOLD_SCRIPT_INCOMPLETE", str(exc))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(prompt, end="" if prompt.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
