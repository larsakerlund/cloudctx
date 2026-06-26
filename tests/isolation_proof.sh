#!/bin/sh
# The headline acceptance test: two contexts must isolate AZURE_CONFIG_DIR so
# that two shells never share Azure login / active-subscription state.
#
# Hermetic — uses a throwaway $CLOUDCTX_HOME, no real Azure/iTerm2 needed.
set -eu

HOME_DIR=$(mktemp -d)
export CLOUDCTX_HOME="$HOME_DIR"
export CLOUDCTX_PROFILES="$HOME_DIR/profiles.json"
CLI="$(CDPATH= cd "$(dirname "$0")/.." && pwd)/cloudctx"

"$CLI" new acme   --display "Acme"   --color "#c0392b" \
  --azure-tenant t-acme   --azure-subscription sub-acme   --no-login --no-profiles >/dev/null
"$CLI" new globex --display "Globex" --color "#2980b9" \
  --azure-tenant t-globex --azure-subscription sub-globex --no-login --no-profiles >/dev/null

# Two independent subshells select different contexts.
A=$(sh -c 'eval "$('"$CLI"' _env acme)";   printf %s "$AZURE_CONFIG_DIR"')
B=$(sh -c 'eval "$('"$CLI"' _env globex)"; printf %s "$AZURE_CONFIG_DIR"')

echo "acme   -> AZURE_CONFIG_DIR=$A"
echo "globex -> AZURE_CONFIG_DIR=$B"

fail=0
[ "$A" != "$B" ] || { echo "FAIL: AZURE_CONFIG_DIR identical across contexts"; fail=1; }
case "$A" in *"/acme/azure")   : ;; *) echo "FAIL: acme dir unexpected";   fail=1 ;; esac
case "$B" in *"/globex/azure") : ;; *) echo "FAIL: globex dir unexpected"; fail=1 ;; esac

rm -rf "$HOME_DIR"
if [ "$fail" = 0 ]; then
  echo "PASS: two contexts isolate AZURE_CONFIG_DIR (no cross-shell bleed)"
  exit 0
fi
exit 1
