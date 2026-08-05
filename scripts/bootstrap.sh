#!/bin/sh
set -eu

EXPECTED_REPO='keiyoaimacmini-png/keiyo-ai-video-workflow'
EXPECTED_ORIGIN='https://github.com/keiyoaimacmini-png/keiyo-ai-video-workflow.git'
EXPECTED_REF='v1.0.0'
MARKETPLACE='keiyo-ai-video-workflow'
PLUGIN_ID='keiyo-product-video@keiyo-ai-video-workflow'

usage() {
  printf '%s\n' "Usage: scripts/bootstrap.sh --repo $EXPECTED_REPO --ref $EXPECTED_REF"
}

repo_slug=''
repo_ref=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; repo_slug=$2; shift 2 ;;
    --ref) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; repo_ref=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'HOLD_UNKNOWN_ARGUMENT %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[ "$repo_slug" = "$EXPECTED_REPO" ] || { printf '%s\n' 'HOLD_REPOSITORY_MISMATCH' >&2; exit 2; }
[ "$repo_ref" = "$EXPECTED_REF" ] || { printf '%s\n' 'HOLD_RELEASE_REF_MISMATCH' >&2; exit 2; }

for command_name in codex gh git python3 sh; do
  command -v "$command_name" >/dev/null 2>&1 || { printf 'HOLD_COMMAND_MISSING %s\n' "$command_name" >&2; exit 2; }
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)

# This package check is intentionally the first state-dependent action. Everything
# before it is argument parsing or command discovery; no installation occurs.
python3 "$repo_root/scripts/verify_package.py"
expected_commit=$(sh "$repo_root/scripts/verify-release.sh")

marketplace_json=$(codex plugin marketplace list --json)
marketplace_record=$(printf '%s' "$marketplace_json" | python3 -c '
import json,sys
rows=json.load(sys.stdin).get("marketplaces", [])
hits=[x for x in rows if isinstance(x,dict) and x.get("name")=="keiyo-ai-video-workflow"]
if len(hits)>1: raise SystemExit(2)
print(json.dumps(hits[0],separators=(",",":")) if hits else "")
') || { printf '%s\n' 'HOLD_MARKETPLACE_READBACK_INVALID' >&2; exit 3; }

verify_marketplace_snapshot() {
  record=$1
  root=$(printf '%s' "$record" | python3 -c '
import json,sys
x=json.load(sys.stdin); s=x.get("marketplaceSource") or {}
ok=s.get("sourceType")=="git" and s.get("source")=="https://github.com/keiyoaimacmini-png/keiyo-ai-video-workflow.git"
root=x.get("root")
raise SystemExit(0 if ok and isinstance(root,str) and root else 1)
' && printf '%s' "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["root"])') || return 1
  [ "$(git -C "$root" remote get-url origin)" = "$EXPECTED_ORIGIN" ] || return 1
  [ "$(git -C "$root" rev-parse HEAD)" = "$expected_commit" ] || return 1
  [ "$(git -C "$root" rev-parse "$EXPECTED_REF^{commit}")" = "$expected_commit" ] || return 1
  [ -z "$(git -C "$root" status --porcelain=v1 --untracked-files=all)" ] || return 1
  [ -z "$(find "$root" -type l -print -quit)" ] || return 1
}

if [ -n "$marketplace_record" ]; then
  verify_marketplace_snapshot "$marketplace_record" || {
    printf '%s\n' 'HOLD_EXISTING_MARKETPLACE_SOURCE_OR_SNAPSHOT_MISMATCH' >&2
    exit 3
  }
else
  codex plugin marketplace add "$EXPECTED_REPO" --ref "$EXPECTED_REF"
  marketplace_json=$(codex plugin marketplace list --json)
  marketplace_record=$(printf '%s' "$marketplace_json" | python3 -c '
import json,sys
hits=[x for x in json.load(sys.stdin).get("marketplaces",[]) if isinstance(x,dict) and x.get("name")=="keiyo-ai-video-workflow"]
raise SystemExit(1 if len(hits)!=1 else 0)
' >/dev/null 2>&1 && printf '%s' "$marketplace_json" | python3 -c '
import json,sys
print(json.dumps(next(x for x in json.load(sys.stdin).get("marketplaces",[]) if x.get("name")=="keiyo-ai-video-workflow"),separators=(",",":")))
') || { printf '%s\n' 'HOLD_MARKETPLACE_ADD_READBACK_FAILED' >&2; exit 3; }
  verify_marketplace_snapshot "$marketplace_record" || { printf '%s\n' 'HOLD_MARKETPLACE_ADD_SNAPSHOT_MISMATCH' >&2; exit 3; }
fi

codex plugin add "$PLUGIN_ID"
plugin_json=$(codex plugin list --json)
plugin_path=$(printf '%s' "$plugin_json" | python3 -c '
import json,sys
hits=[x for x in json.load(sys.stdin).get("installed",[]) if isinstance(x,dict) and x.get("pluginId")=="keiyo-product-video@keiyo-ai-video-workflow"]
if len(hits)!=1: raise SystemExit(1)
x=hits[0]; source=x.get("source") or {}; market=x.get("marketplaceSource") or {}
ok=(x.get("name")=="keiyo-product-video" and x.get("marketplaceName")=="keiyo-ai-video-workflow" and x.get("version")=="1.0.0" and x.get("installed") is True and x.get("enabled") is True and source.get("source")=="local" and isinstance(source.get("path"),str) and market.get("sourceType")=="git" and market.get("source")=="https://github.com/keiyoaimacmini-png/keiyo-ai-video-workflow.git")
if not ok: raise SystemExit(1)
print(source["path"])
') || { printf '%s\n' 'HOLD_PLUGIN_READBACK_MISMATCH' >&2; exit 3; }

marketplace_root=$(printf '%s' "$marketplace_record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["root"])')
[ "$(git -C "$marketplace_root" rev-parse HEAD)" = "$expected_commit" ] || {
  printf '%s\n' 'HOLD_INSTALLED_SNAPSHOT_MISMATCH' >&2; exit 3;
}
[ "$(CDPATH= cd -- "$plugin_path" && pwd -P)" = "$(CDPATH= cd -- "$marketplace_root/plugins/keiyo-product-video" && pwd -P)" ] || {
  printf '%s\n' 'HOLD_PLUGIN_SOURCE_PATH_MISMATCH' >&2; exit 3;
}
case "$(CDPATH= cd -- "$plugin_path" && pwd -P)/" in
  "$(CDPATH= cd -- "$marketplace_root" && pwd -P)/"*) ;;
  *) printf '%s\n' 'HOLD_PLUGIN_SOURCE_OUTSIDE_MARKETPLACE' >&2; exit 3 ;;
esac

python3 - "$repo_root" "$marketplace_root" "$plugin_path" <<'PY'
import hashlib, pathlib, sys
release, snapshot, installed = map(pathlib.Path, sys.argv[1:])
entries={}
for line in (release/"MANIFEST.sha256").read_text().splitlines():
    digest,relative=line.split("  ",1); entries[relative]=digest
if hashlib.sha256((release/"MANIFEST.sha256").read_bytes()).digest()!=hashlib.sha256((snapshot/"MANIFEST.sha256").read_bytes()).digest():
    raise SystemExit(1)
files={
 "plugins/keiyo-product-video/.codex-plugin/plugin.json":".codex-plugin/plugin.json",
 "plugins/keiyo-product-video/skills/create-tiktok-product-video/SKILL.md":"skills/create-tiktok-product-video/SKILL.md",
 "plugins/keiyo-product-video/skills/create-tiktok-product-video/agents/openai.yaml":"skills/create-tiktok-product-video/agents/openai.yaml",
 "plugins/keiyo-product-video/skills/create-tiktok-product-video/references/payload_contract.md":"skills/create-tiktok-product-video/references/payload_contract.md",
 "plugins/keiyo-product-video/skills/create-tiktok-product-video/scripts/validate_product_video_payload.py":"skills/create-tiktok-product-video/scripts/validate_product_video_payload.py",
}
for release_relative,plugin_relative in files.items():
    digest=entries.get(release_relative)
    paths=(release/release_relative, snapshot/release_relative, installed/plugin_relative)
    if not digest or any(not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest for p in paths):
        raise SystemExit(1)
PY

printf 'PASS_PLUGIN_INSTALLED commit=%s version=1.0.0\n' "$expected_commit"
printf '%s\n' 'Start a new Codex task before using $create-tiktok-product-video.'
