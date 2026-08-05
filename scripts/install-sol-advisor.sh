#!/bin/sh
set -eu

OFFICIAL_REPO='DannyMac180/sol-advisor'
OFFICIAL_ORIGIN='https://github.com/DannyMac180/sol-advisor.git'
MARKETPLACE='sol-advisor'
PLUGIN_ID='sol-advisor@sol-advisor'

for command_name in codex git jq python3 sh; do
  command -v "$command_name" >/dev/null 2>&1 || { printf 'HOLD_COMMAND_MISSING %s\n' "$command_name" >&2; exit 2; }
done

remote_main=$(git ls-remote "$OFFICIAL_ORIGIN" refs/heads/main | python3 -c 'import sys; line=sys.stdin.read().strip(); print(line.split()[0] if line else "")')
[ -n "$remote_main" ] || { printf '%s\n' 'HOLD_SOL_ADVISOR_REMOTE_MAIN_UNVERIFIED' >&2; exit 3; }

marketplace_json=$(codex plugin marketplace list --json)
marketplace_record=$(printf '%s' "$marketplace_json" | python3 -c '
import json,sys
hits=[x for x in json.load(sys.stdin).get("marketplaces",[]) if isinstance(x,dict) and x.get("name")=="sol-advisor"]
if len(hits)>1: raise SystemExit(2)
print(json.dumps(hits[0],separators=(",",":")) if hits else "")
') || { printf '%s\n' 'HOLD_SOL_ADVISOR_MARKETPLACE_READBACK_INVALID' >&2; exit 3; }

verify_official_marketplace() {
  record=$1
  root=$(printf '%s' "$record" | python3 -c '
import json,sys
x=json.load(sys.stdin); source=x.get("marketplaceSource") or {}; root=x.get("root")
ok=source.get("sourceType")=="git" and source.get("source")=="https://github.com/DannyMac180/sol-advisor.git" and isinstance(root,str) and root
raise SystemExit(0 if ok else 1)
print(root)
') || return 1
  [ "$(git -C "$root" remote get-url origin)" = "$OFFICIAL_ORIGIN" ] || return 1
  [ "$(git -C "$root" rev-parse HEAD)" = "$remote_main" ] || return 1
  [ -z "$(git -C "$root" status --porcelain=v1 --untracked-files=all)" ] || return 1
  [ -z "$(find "$root" -type l -print -quit)" ] || return 1
}

if [ -n "$marketplace_record" ]; then
  printf '%s' "$marketplace_record" | python3 -c '
import json,sys
x=json.load(sys.stdin); s=x.get("marketplaceSource") or {}
raise SystemExit(0 if s.get("sourceType")=="git" and s.get("source")=="https://github.com/DannyMac180/sol-advisor.git" else 1)
' || { printf '%s\n' 'HOLD_SOL_ADVISOR_MARKETPLACE_SOURCE_CONFLICT' >&2; exit 3; }
  if ! verify_official_marketplace "$marketplace_record"; then
    codex plugin marketplace upgrade "$MARKETPLACE"
  fi
else
  codex plugin marketplace add "$OFFICIAL_REPO" --ref main
fi

marketplace_json=$(codex plugin marketplace list --json)
marketplace_record=$(printf '%s' "$marketplace_json" | python3 -c '
import json,sys
hits=[x for x in json.load(sys.stdin).get("marketplaces",[]) if isinstance(x,dict) and x.get("name")=="sol-advisor"]
if len(hits)!=1: raise SystemExit(1)
print(json.dumps(hits[0],separators=(",",":")))
') || { printf '%s\n' 'HOLD_SOL_ADVISOR_MARKETPLACE_MISSING' >&2; exit 3; }
verify_official_marketplace "$marketplace_record" || { printf '%s\n' 'HOLD_SOL_ADVISOR_SNAPSHOT_NOT_CURRENT_MAIN' >&2; exit 3; }

codex plugin add "$PLUGIN_ID"
plugin_json=$(codex plugin list --json)
plugin_path=$(printf '%s' "$plugin_json" | python3 -c '
import json,sys,pathlib
hits=[x for x in json.load(sys.stdin).get("installed",[]) if isinstance(x,dict) and x.get("pluginId")=="sol-advisor@sol-advisor"]
if len(hits)!=1: raise SystemExit(1)
x=hits[0]; source=x.get("source") or {}; market=x.get("marketplaceSource") or {}
ok=x.get("name")=="sol-advisor" and x.get("marketplaceName")=="sol-advisor" and isinstance(x.get("version"),str) and bool(x.get("version")) and x.get("installed") is True and x.get("enabled") is True and source.get("source")=="local" and isinstance(source.get("path"),str) and market.get("sourceType")=="git" and market.get("source")=="https://github.com/DannyMac180/sol-advisor.git"
if not ok: raise SystemExit(1)
path=pathlib.Path(source["path"])
required=[".codex-plugin/plugin.json","scripts/install-agents.sh"]
if any(not (path/item).is_file() or (path/item).is_symlink() for item in required): raise SystemExit(1)
manifest=json.loads((path/".codex-plugin/plugin.json").read_text())
if manifest.get("name")!="sol-advisor" or manifest.get("version")!=x.get("version"): raise SystemExit(1)
print(path)
') || { printf '%s\n' 'HOLD_SOL_ADVISOR_PLUGIN_READBACK_MISMATCH' >&2; exit 3; }

marketplace_root=$(printf '%s' "$marketplace_record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["root"])')
[ "$(CDPATH= cd -- "$plugin_path" && pwd -P)" = "$(CDPATH= cd -- "$marketplace_root/plugins/sol-advisor" && pwd -P)" ] || {
  printf '%s\n' 'HOLD_SOL_ADVISOR_SOURCE_PATH_MISMATCH' >&2; exit 3;
}
case "$(CDPATH= cd -- "$plugin_path" && pwd -P)/" in
  "$(CDPATH= cd -- "$marketplace_root" && pwd -P)/"*) ;;
  *) printf '%s\n' 'HOLD_SOL_ADVISOR_SOURCE_OUTSIDE_MARKETPLACE' >&2; exit 3 ;;
esac

python3 - "$marketplace_root" "$plugin_path" <<'PY'
import hashlib,pathlib,sys
snapshot,installed=map(pathlib.Path,sys.argv[1:])
files=[
 ".codex-plugin/plugin.json",
 "skills/orchestration/SKILL.md",
 "scripts/install-agents.sh",
 "agents/sol-advisor-terra-implementer.toml",
 "agents/sol-advisor-sol-reviewer.toml",
]
for relative in files:
    source=snapshot/"plugins/sol-advisor"/relative
    target=installed/relative
    if any(not p.is_file() or p.is_symlink() for p in (source,target)):
        raise SystemExit(1)
    if hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(target.read_bytes()).digest():
        raise SystemExit(1)
installer=(installed/"scripts/install-agents.sh").read_text()
for template in ("sol-advisor-terra-implementer.toml","sol-advisor-sol-reviewer.toml"):
    if template not in installer:
        raise SystemExit(1)
PY

sh "$plugin_path/scripts/install-agents.sh"
sh "$plugin_path/scripts/install-agents.sh" --check

agent_root=${CODEX_HOME:-"$HOME/.codex"}
python3 - "$plugin_path" "$agent_root/agents" <<'PY'
import pathlib,re,sys
plugin,agents=map(pathlib.Path,sys.argv[1:])
roles={
 "sol-advisor-terra-implementer.toml":("sol_advisor_terra_implementer","gpt-5.6-terra"),
 "sol-advisor-sol-reviewer.toml":("sol_advisor_sol_reviewer","gpt-5.6-sol"),
}
for filename,(name,model) in roles.items():
    template=plugin/"agents"/filename
    installed=agents/filename
    if any(not p.is_file() or p.is_symlink() for p in (template,installed)):
        raise SystemExit(1)
    if template.read_bytes()!=installed.read_bytes():
        raise SystemExit(1)
    text=installed.read_text()
    def scalar(key):
        values=re.findall(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]+)"\s*$',text)
        return values[0] if len(values)==1 else None
    if scalar("name")!=name or scalar("model")!=model or scalar("model_reasoning_effort")!="high":
        raise SystemExit(1)
PY

printf 'PASS_SOL_ADVISOR_PLUGIN commit=%s\n' "$remote_main"
printf '%s\n' 'HOLD_MODEL_AVAILABILITY_UNVERIFIED'
printf '%s\n' 'Open a new Codex task, confirm GPT-5.6 Sol / High and Terra / High in the UI, and do not use Luna unless explicitly authorized.'
exit 4
