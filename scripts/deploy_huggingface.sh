#!/usr/bin/env bash
# Deploy the Streamlit dashboard to a Hugging Face Space — no interactive login.
#
# Prereqs:
#   • An HF account + a WRITE access token: https://huggingface.co/settings/tokens
#   • git, python3
#
# Usage:
#   export HF_TOKEN=hf_xxx
#   ./scripts/deploy_huggingface.sh <username>/<space-name>
#   # e.g. ./scripts/deploy_huggingface.sh fai287/snowflake-cortexai-mapper
#
# What it does:
#   1. Creates the Space (streamlit SDK) if it doesn't exist.
#   2. Builds a temp copy of the repo with the HF YAML header prepended to
#      README.md (keeps the GitHub README clean).
#   3. Force-pushes that copy to the Space. HF builds + serves it automatically.
set -euo pipefail

SPACE_ID="${1:-}"
if [[ -z "$SPACE_ID" || "${HF_TOKEN:-}" == "" ]]; then
  echo "Usage: HF_TOKEN=hf_xxx $0 <username>/<space-name>" >&2
  exit 1
fi
HF_USERNAME="${SPACE_ID%%/*}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "▶ Ensuring Space '$SPACE_ID' exists (streamlit SDK)…"
python3 - <<PY
import os, sys
try:
    from huggingface_hub import create_repo
except ImportError:
    os.system(f"{sys.executable} -m pip install -q huggingface_hub")
    from huggingface_hub import create_repo
create_repo("$SPACE_ID", repo_type="space", space_sdk="streamlit",
            token="$HF_TOKEN", exist_ok=True)
print("  ok")
PY

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "▶ Staging repo copy in $WORK…"
git -C "$ROOT" archive --format=tar HEAD | tar -x -C "$WORK"

# Prepend HF metadata header to the README copy that goes to the Space.
cat "$ROOT/deploy/huggingface/space_metadata.md" "$ROOT/README.md" > "$WORK/README.md"

cd "$WORK"
git init -q && git checkout -q -b main
git config user.name "hf-deploy"
git config user.email "hf-deploy@local"
git add -A && git commit -q -m "Deploy dashboard to Hugging Face Spaces"
echo "▶ Pushing to https://huggingface.co/spaces/$SPACE_ID …"
git push -q --force "https://${HF_USERNAME}:${HF_TOKEN}@huggingface.co/spaces/${SPACE_ID}" main

echo "✅ Done. Your dashboard will be live in ~1-2 min at:"
echo "   https://huggingface.co/spaces/${SPACE_ID}"
