#!/bin/sh
set -eu

EXPECTED_ACCOUNT='keiyoaimacmini-png'
EXPECTED_REPO='keiyoaimacmini-png/keiyo-ai-video-workflow'
EXPECTED_ORIGIN='https://github.com/keiyoaimacmini-png/keiyo-ai-video-workflow.git'
EXPECTED_TAG='v1.0.0'

for command_name in gh git python3; do
  command -v "$command_name" >/dev/null 2>&1 || { printf 'HOLD_COMMAND_MISSING %s\n' "$command_name" >&2; exit 2; }
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)

[ "$(gh api user --jq .login)" = "$EXPECTED_ACCOUNT" ] || { printf '%s\n' 'HOLD_GITHUB_ACCOUNT_MISMATCH' >&2; exit 3; }

repo_json=$(gh repo view "$EXPECTED_REPO" --json nameWithOwner,isPrivate,defaultBranchRef,url)
printf '%s' "$repo_json" | python3 -c '
import json,sys
x=json.load(sys.stdin)
ok=x.get("nameWithOwner")=="keiyoaimacmini-png/keiyo-ai-video-workflow" and x.get("isPrivate") is True and (x.get("defaultBranchRef") or {}).get("name")=="main" and x.get("url")=="https://github.com/keiyoaimacmini-png/keiyo-ai-video-workflow"
raise SystemExit(0 if ok else 1)
' || { printf '%s\n' 'HOLD_PRIVATE_REPOSITORY_METADATA_MISMATCH' >&2; exit 3; }

[ "$(git -C "$repo_root" remote get-url origin)" = "$EXPECTED_ORIGIN" ] || { printf '%s\n' 'HOLD_LOCAL_ORIGIN_MISMATCH' >&2; exit 3; }
[ "$(git -C "$repo_root" branch --show-current)" = 'main' ] || { printf '%s\n' 'HOLD_LOCAL_BRANCH_NOT_MAIN' >&2; exit 3; }
[ -z "$(git -C "$repo_root" status --porcelain=v1 --untracked-files=all)" ] || { printf '%s\n' 'HOLD_WORKTREE_NOT_CLEAN' >&2; exit 3; }
[ "$(git -C "$repo_root" cat-file -t "refs/tags/$EXPECTED_TAG")" = 'tag' ] || { printf '%s\n' 'HOLD_ANNOTATED_LOCAL_TAG_REQUIRED' >&2; exit 3; }

head_commit=$(git -C "$repo_root" rev-parse HEAD)
tag_commit=$(git -C "$repo_root" rev-parse "$EXPECTED_TAG^{commit}")
[ "$head_commit" = "$tag_commit" ] || { printf '%s\n' 'HOLD_HEAD_TAG_MISMATCH' >&2; exit 3; }

remote_refs=$(git -C "$repo_root" ls-remote origin refs/heads/main "refs/tags/$EXPECTED_TAG" "refs/tags/$EXPECTED_TAG^{}")
printf '%s' "$remote_refs" | python3 -c '
import sys
rows={ref:sha for sha,ref in (line.split("\t",1) for line in sys.stdin.read().splitlines() if "\t" in line)}
head=sys.argv[1]
ok=rows.get("refs/heads/main")==head and rows.get("refs/tags/v1.0.0^{}")==head and "refs/tags/v1.0.0" in rows
raise SystemExit(0 if ok else 1)
' "$head_commit" || { printf '%s\n' 'HOLD_REMOTE_MAIN_TAG_COMMIT_MISMATCH' >&2; exit 3; }

printf '%s\n' "$head_commit"

