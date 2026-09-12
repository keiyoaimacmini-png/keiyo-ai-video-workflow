# CapCut TTS: normal Chrome via Playwright MCP

Holiday Twist generation uses this Mac's already-running **Google Chrome.app**, not Cursor's built-in browser.

## Routine path

1. Google Chrome.app is already running.
2. Cursor connects through this project's **Playwright MCP** with `--cdp-endpoint=chrome`.
3. Resolve whichever Playwright MCP is available in this session. Do not hard-code an MCP namespace string; namespace names are host-dependent. If the first attach fails, retry up to 3 times before HOLD.
4. Open CapCut official Text to Speech on that attached Chrome session. Do not click Generate during preflight.

`.cursor/mcp.json` is a local host setting. Do not add it to Git.

## Do not

- Do not fall back to `cursor-ide-browser`.
- Do not fall back to an extension-based CapCut adapter.
- Do not copy cookies, spoof User-Agent, or call unpublished CapCut internals.

## When the MCP cannot attach

Retry up to 3 times. Do not ask the operator about a transient miss. If 127.0.0.1:9222 is already listening, Chrome Remote Debugging is READY — do not tell the operator to allow remote debugging again. If Playwright still cannot attach, stop with `HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE` and record the MCP attach error gist. During start-time preflight, keep checking the other independent items and include genuine operator fixes in one **開始前に直すこと** list.

Operator setup, only when 9222 is not listening (no secrets):

1. Start Google Chrome.app on this Mac.
2. In this project's local `.cursor/mcp.json` (untracked), configure Playwright MCP args to include `--cdp-endpoint=chrome`.
3. Refresh the MCP tool list in Cursor after that config exists.
4. Confirm the project Playwright MCP can attach to the running Chrome, then retry CapCut TTS.

Login, CAPTCHA, 2FA, or account choice on CapCut still stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`.
