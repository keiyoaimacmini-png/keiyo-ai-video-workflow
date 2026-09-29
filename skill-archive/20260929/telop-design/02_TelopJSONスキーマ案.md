# Telop JSONスキーマ案

**設計段階・未実装。** この案は、要件書の§7、§8、§16、§21を一つの受け渡し形式にまとめたもの。現行の台本、rough-edit、ChatCutをこの案だけで変更・有効化しない。

## 1. 先に決める形

Telop JSONは、テロップ1件分の「何を、どの見た目で、いつ、どこに出すか」を表す機械向けのメモとする。要件書の例には、同じ意味を別の書き方で表した項目があるため、実装時は次のように一つへ寄せる。

| 要件書に出てくる書き方 | この案での扱い |
|---|---|
| `font_style` | `font.family` にまとめる |
| `base_color` と `outline` | `text_style.base_color` と `text_style.outline` にまとめる |
| `animation_in` / `animation_out` | `animation.in` / `animation.out` にまとめる |
| 要件書§7の `pop_soft` | `pop` に統合（案） |
| `emoji` 配列 | 表示順を持つ `elements` の中の `type: "emoji"` 要素にまとめる |
| 部分強調の配列と全文強調の指定 | `emphasis.mode` と `emphasis.items` にまとめる |

この統合は項目の重複を避けるための設計案であり、要件を増やすものではない。

## 2. Telop Generation AIが出す項目

Telop Generation AIは、セリフの意味メタデータを見て、定義済みの見た目を選ぶ。開始・終了時間と最終位置は出さない。

| 項目 | 必須 | 内容 | 制約 |
|---|---:|---|---|
| `text` | ○ | 画面に出す本文。セリフ本文と同じ文字列 | セリフ本文にない語を足さない。絵文字は入れず、絵文字要素を別に持つ |
| `type` | ○ | テロップの種別 | 列挙値から1つ |
| `importance` | ○ | 重要度。見た目を選ぶときの手がかり | `NORMAL` / `HIGH` / `VERY_HIGH` |
| `font` | ○ | フォントの種類と太さ | `family` と `weight` を持つ |
| `text_style` | ○ | 本文の色と縁取り | 初期デザインシステムの色から選ぶ |
| `emphasis` | ○ | どの語を目立たせるか | 本文に実在する語句だけ。部分強調は最大2個 |
| `elements` | ○ | 本文と絵文字の表示順 | `text` と `emoji` を別要素にする |
| `animation` | ○ | テロップの入る動きと消える動き | 初期モーションの列挙値から選ぶ |

`importance`はGeminiの意味メタデータを引き継ぐ項目であり、Telop Generation AIが時間や位置を決めるための項目ではない。

### Generation AIの出力例

```json
{
  "text": "これスマホだけで簡単に操作できる",
  "type": "EMPHASIS",
  "importance": "HIGH",
  "font": {
    "family": "rounded_bold",
    "weight": 700
  },
  "text_style": {
    "base_color": "white",
    "outline": {
      "color": "black",
      "width": 8
    }
  },
  "emphasis": {
    "mode": "partial",
    "items": [
      {
        "text": "スマホだけで",
        "color": "yellow"
      },
      {
        "text": "簡単",
        "color": "yellow"
      }
    ]
  },
  "elements": [
    {
      "type": "text",
      "value": "これスマホだけで簡単に操作できる"
    },
    {
      "type": "emoji",
      "value": "📱",
      "animation": "pop_soft"
    }
  ],
  "animation": {
    "in": "pop",
    "out": "fade_short"
  }
}
```

## 3. Editing AIが追加する項目

Editing AIは映像とカットの情報を見て、生成済みのデザインへ時間と位置を足す。位置は0〜1の正規化座標（画面の幅・高さを1とした値）とする。

| 項目 | 必須になる段階 | 内容 | 制約 |
|---|---:|---|---|
| `start` | Rendererに渡すとき | 表示開始時間（秒） | `end`より小さい数値 |
| `end` | Rendererに渡すとき | 表示終了時間（秒） | `start`より大きい数値 |
| `position` | Phase 2のEditing AI後 | 表示位置 | `x` と `y` を持ち、それぞれ0〜1 |

商品、人物、顔、手元、重要UI、TikTok UIを避ける判断はEditing AIの責任である。最小のJSONでは、回避した対象を自由文で増やさず、判断結果としての位置だけを受け取る。Phase 1はEditing AIを有効にせず、現行の固定位置を既定値として扱う。具体的な既定値は現行rough-editを参照する。

### Editing AIの追加例

```json
{
  "start": 4.2,
  "end": 7.1,
  "position": {
    "x": 0.5,
    "y": 0.18
  }
}
```

## 4. Rendererに渡す完成形

Rendererは、Generation AIの項目とEditing AIの追加項目を合わせたものを受け取る。Rendererは内容を再解釈せず、フォントを探し直したり、色を選び直したりしない。本文の改行はRendererの表示処理で行うが、文字の追加・削除・並べ替えはしない。

### Renderer入力のフィールド一覧

| 項目 | 入力元 | Rendererでの扱い |
|---|---|---|
| `text` | Telop Generation AI | 表示本文の正本としてそのまま使う |
| `type` / `importance` | Telop Generation AIとGeminiのメタデータ | 対応する定義済みスタイルを確認する。自由な再選択はしない |
| `font` / `text_style` | Telop Generation AI | フォント、本文色、縁取りを描く |
| `emphasis` | Telop Generation AI | 本文内の実在語句だけを部分色または全文色で描く |
| `elements` | Telop Generation AI | 本文と絵文字を別オブジェクトとして、指定順に描く |
| `animation` | Telop Generation AI | 入りと出の動きを指定どおりに描く |
| `start` / `end` | Editing AIまたは既存の編集計画 | 描画する時間範囲にする |
| `position` | Editing AIまたはPhase 1の既定値 | 表示基準位置にする |

### Renderer入力の完成例

```json
{
  "text": "徹底比較！",
  "type": "COMPARE",
  "importance": "VERY_HIGH",
  "font": {
    "family": "bold_square",
    "weight": 900
  },
  "text_style": {
    "base_color": "white",
    "outline": {
      "color": "black",
      "width": 8
    }
  },
  "emphasis": {
    "mode": "full",
    "items": [
      {
        "text": "徹底比較！",
        "color": "yellow"
      }
    ]
  },
  "elements": [
    {
      "type": "text",
      "value": "徹底比較！"
    }
  ],
  "animation": {
    "in": "pop",
    "out": "fade_short"
  },
  "position": {
    "x": 0.5,
    "y": 0.2
  },
  "start": 0.0,
  "end": 2.5
}
```

## 5. 列挙値と検査ルール案

### 5.1 テロップ種別

`type` は次のいずれか1つ。

`NORMAL` / `HOOK` / `EMPHASIS` / `COMPARE` / `NOTICE` / `SALE` / `PRICE` / `CTA`

### 5.2 フォント

| 項目 | 値 | 用途 |
|---|---|---|
| `font.family` | `rounded_bold` | 通常説明寄りの丸ゴシック系 |
| `font.family` | `bold_square` | HOOK、強調、比較寄りの角ゴシック系 |
| `font.weight` | `700` / `900` | 定義済みの太さ。700は設計案の値（要件書§21は900のみ） |

### 5.3 色と縁取り

| 項目 | 許可値 |
|---|---|
| `text_style.base_color` | `white` / `yellow` / `red` / `pink` / `pale_orange` |
| `emphasis.items[].color` | `yellow` / `red` / `pink` / `pale_orange` |
| `text_style.outline.color` | `black` |

1件のテロップ内で使う色数は、要件書の初期ルールに合わせて少数に制限する。現行字幕側の1行・2色制限と、Renderer側でどの検査を共通化するかは `05_確認事項.md` で保留する。

### 5.4 強調

`emphasis.mode` は `none` / `full` / `partial` のいずれか。

- `none`：`items`は空にする。
- `full`：本文全体を1件の強調対象にする。
- `partial`：本文に実在する語句を最大2件まで指定する。
- `items[].text`は、`text`にそのまま現れる語句だけにする。言い換えや、本文にない補足語は受け付けない。

### 5.5 要素と絵文字

`elements[].type` は `text` または `emoji`。`emoji`の候補は初期許可リストから選ぶ。

`🔥` / `✨` / `📱` / `🚗` / `⚠️` / `🎁` / `💡` / `💧` / `🔋` / `😳` / `👀` / `✅`

本文の文字は`text`要素、絵文字は`emoji`要素に分ける。絵文字の表示アニメーションは、本文の意味や文字列を変えない。
- 不変条件：`type: "text"` の `elements` の `value` を連結した文字列 == 最上位の `text`。

### 5.6 モーション

| 場所 | 許可値 |
|---|---|
| `animation.in` | `pop` / `soft_slide` |
| `animation.out` | `fade_short` / `cut` |
| `elements[].animation`（絵文字） | `pop_soft` / `pop` |

基本は静止して読める時間を残す。回転や過剰なバウンドなど、初期列挙値にない動きを自由入力させない。

### 5.7 時間と位置

- `start`と`end`は秒数で、`start < end`を満たす。
- `position.x`と`position.y`は0以上1以下。
- Phase 1では位置が欠けたGeneration出力をそのままChatCutへ渡さない。プレビュー用の既定値を入れるか、現在の字幕手順で扱うかを工程側で明示する。
- Phase 2ではEditing AIの位置を使う。固定値を自動で上書きしない。

## 6. `edit-plan.json`との関係は未確定

現行の`edit-plan.json`は、映像、音声、時間、字幕本文、表示用の改行を実行する計画である。一方、Telop JSONは見た目と、将来は時間・位置を持つ。二つのファイルで同じ時間・本文・改行を持つと、食い違いの原因になる。

この設計案では、Telop JSONを見た目の正本、`edit-plan.json`をタイムライン実行の正本として参照関係を作る方向をおすすめするが、連携キー、重複する時間の扱い、`caption_visual_wrap`をどちらが持つかは `05_確認事項.md` で決めずに保留する。
