# Record a correction

When the operator corrects this case, fix the current draft **and** record a lesson in the same turn.

1. Classify: quality (script, picture, captions, TTS, timing, wording) vs safety (new checkpoint, overwrite, Drive/TTS procedure, HOLD definition).
2. Quality: `record_lesson.py` without `--safety`. It writes `active/` and the next case loads it.
3. Safety: `record_lesson.py --safety`. Tell the operator it is pending. Do not edit the portable skill.
4. Rebuild only the affected craft artifact and rerun that surface's gate before asking the same checkpoint again.
5. Do not append paragraphs to portable `core-invariants.md` or `AGENTS.md` for a quality miss.
