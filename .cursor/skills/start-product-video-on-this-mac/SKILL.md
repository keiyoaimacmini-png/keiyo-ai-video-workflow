---
name: start-product-video-on-this-mac
description: Start a new TikTok product-video case on Cursor Desktop on this Mac. Use when the user wants このMac, a remade 台本, or cannot select This Mac in a Cloud chat.
disable-model-invocation: true
---

# Start product video on this Mac

## If this process is a Cloud Agent

Stop. Do not create a case, open Gemini, or continue production.

Tell the user in Japanese, plainly:

- 今の会話は雲のパソコン用なので、「このMac」は灰色で押せない。壊れていない。
- 台本は作り直してよい。
- コードが見える Cursor の画面で、新しい Agent チャットを開く。
- そこに次を貼る。

```text
/produce-tiktok-product-video-portable

このMacで、新しい台本から始めてください。
雲の会話は使わないでください。

製品はAN-S182です。
新しい案件として、台本OKまで進めて止めてください。
台本は、このMacのChromeのGeminiで作ってください。
```

Do not tell them to press Set up Environment. That button is for Cloud, not for This Mac.

## If this process is Cursor Desktop on the operator Mac

Follow `.cursor/skills/produce-tiktok-product-video-portable/SKILL.md`.

- Create a **new** case. Do not reopen a COMPLETE case.
- Remaking the script is allowed.
- Open official Gemini Web in **this Mac's Chrome** only. Do not use a Cloud VM session. Do not call the Gemini API.
- Prefer Gemini 3.8 Flash when visible; otherwise the visible Flash.
- After frame inventory, paste only the output of `scripts/render_gemini_web_prompt.py`.
- Stop at Checkpoint 1 (`台本OK`).
