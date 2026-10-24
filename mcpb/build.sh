#!/usr/bin/env bash
# Build the HyperTTS MCP Bridge as a .mcpb bundle for Claude Desktop.
#
#   ./mcpb/build.sh
#
# Output: dist/hypertts-mcp-bridge-<version>.mcpb
#
# The version comes from mcp_server/package.json and replaces the "version"
# in mcpb/manifest.json in the staged copy.
#
# Assembles a staging tree (manifest.json + server/ with a lockfile-exact,
# production-only node_modules) and runs `mcpb pack` on it. Requires network
# for `npm ci` and `npx @anthropic-ai/mcpb`.
set -euo pipefail

# Pinned so a new (or compromised) mcpb release can't change what goes into a
# release bundle unnoticed. To upgrade: check `npm view @anthropic-ai/mcpb
# version`, update this, rebuild, and confirm the bundle installs in Claude
# Desktop.
MCPB_VERSION="2.1.2"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
stage="$here/dist/mcpb-stage"
version="$(node -p "require('$here/mcp_server/package.json').version")"
out="$here/dist/hypertts-mcp-bridge-$version.mcpb"

rm -rf "$stage"
mkdir -p "$stage/server" "$here/dist"

node -e '
  const fs = require("fs");
  const [src, dst, version] = process.argv.slice(1);
  const m = JSON.parse(fs.readFileSync(src, "utf8"));
  m.version = version;
  fs.writeFileSync(dst, JSON.stringify(m, null, 2) + "\n");
' "$here/mcpb/manifest.json" "$stage/manifest.json" "$version"
cp "$here/mcp_server/index.js"          "$stage/server/index.js"
cp "$here/mcp_server/package.json"      "$stage/server/package.json"
cp "$here/mcp_server/package-lock.json" "$stage/server/package-lock.json"

( cd "$stage/server" && npm ci --omit=dev --no-audit --no-fund )

npx --yes "@anthropic-ai/mcpb@$MCPB_VERSION" validate "$stage/manifest.json"
npx --yes "@anthropic-ai/mcpb@$MCPB_VERSION" pack "$stage" "$out"

echo
echo "built: $out"
