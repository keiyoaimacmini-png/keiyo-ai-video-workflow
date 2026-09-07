# Before 台本OK

Portable work may already be at `SCRIPT_PREPARED` or unapproved `SCRIPT_REVIEW`. Do not ask `台本OK` yet.

1. Load script lessons (`load_lessons.py --surface script`).
2. Render the Gemini paste with v3 `render_gemini_web_prompt.py` so rejected/accepted pairs are in the prompt.
3. After spoken lines exist, write a craft-script artifact (dialogue only is enough).
4. Run `validate_craft_quality.py --surface script`.
5. If it HOLDs, revise the spoken lines and rerun. Do not present Checkpoint 1.
6. Only then follow portable `stages/02-validate-script.md` presentation rules: show spoken script, six-stage order, hook problem, and spoken solution. Do not make that stop wait on contact sheets.
