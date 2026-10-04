#!/usr/bin/env bash
# Build the HyperTTS MCP Bridge as a .mcpb bundle for Claude Desktop.
#
#   ./mcpb/build.sh
#
# Output: dist/hypertts-mcp-bridge.mcpb
#
# Assembles a staging tree (manifest.json + server/ with a lockfile-exact,
# production-only node_modules) and runs `mcpb pack` on it. Requires network
# for `npm ci` and `npx @anthropic-ai/mcpb`.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # hypertts-mcp-bridge/
stage="$here/dist/mcpb-stage"
out="$here/dist/hypertts-mcp-bridge.mcpb"

rm -rf "$stage"
mkdir -p "$stage/server" "$here/dist"

cp "$here/mcpb/manifest.json" "$stage/manifest.json"
cp "$here/mcp_server/index.js"          "$stage/server/index.js"
cp "$here/mcp_server/package.json"      "$stage/server/package.json"
cp "$here/mcp_server/package-lock.json" "$stage/server/package-lock.json"

( cd "$stage/server" && npm ci --omit=dev --no-audit --no-fund )

npx --yes @anthropic-ai/mcpb@latest validate "$stage/manifest.json"
npx --yes @anthropic-ai/mcpb@latest pack "$stage" "$out"

echo
echo "built: $out"
