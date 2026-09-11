# CapCut TTS: normal Chrome via Playwright MCP

Holiday Twist generation uses this Mac's already-running **Google Chrome.app**, not Cursor's built-in browser.

## Routine path

1. Google Chrome.app is already running.
2. Cursor connects through this project's **Playwright MCP** with `--cdp-endpoint=chrome`.
3. Resolve whichever Playwright MCP is available in this session. Do not hard-code an MCP namespace string; namespace names are host-dependent.
4. Open CapCut official Text to Speech on that attached Chrome session.

`.cursor/mcp.json` is a local host setting. Do not add it to Git.

## Do not

- Do not fall back to `cursor-ide-browser`.
- Do not fall back to an extension-based CapCut adapter.
- Do not copy cookies, spoof User-Agent, or call unpublished CapCut internals.

## When the MCP cannot attach

Stop with `HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE`. Tell the operator the local setup; do not invent another browser path.

Operator setup (no secrets):

1. Start Google Chrome.app on this Mac.
2. In this project's local `.cursor/mcp.json` (untracked), configure Playwright MCP args to include `--cdp-endpoint=chrome`.
3. Refresh the MCP tool list in Cursor after that config exists.
4. Confirm the project Playwright MCP can attach to the running Chrome, then retry CapCut TTS.

Login, CAPTCHA, 2FA, or account choice on CapCut still stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`.
