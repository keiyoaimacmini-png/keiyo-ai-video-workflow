# Portability notes

This package preserves the production contract and removes host-specific orchestration.

Removed:

- assistant-specific project memory commands, encrypted-note hooks, and chat logging;
- assistant-specific subagent routing and reviewer metadata;
- assistant-specific browser, connector, and desktop tool names;
- local vault locations and machine-specific absolute paths;
- provider UI metadata files.

Retained because they are workflow requirements rather than host dependencies:

- CapCut Web as the target editor;
- the exact three Japanese approval texts;
- product settings as the single source of truth;
- exact asset/media hashes, source ranges, timing, mute, rendered-frame, playback, and reload checks;
- one settings-bounded common narration speed and three-layer boundary closure;
- optional exact-scope Drive delivery and read-back;
- fail-closed HOLD behavior, no overwrite, no unknown-result retry, and no automatic deletion.

Five bundled timeline/workflow validators are copied from the verified source implementation without semantic changes. The payload validator retains every production safety check but makes the unused external-routing compatibility extension optional; enabling that extension restores its full strict receipt checks. The host-neutral rule snapshot builder replaces the prior machine-local learning-note source.
