"""Package the Anki add-on as dist/hypertts_mcp_bridge.ankiaddon.

    python3 build_addon.py

Generates manifest.json at build time (so "mod" is always fresh) and zips it
with the files in anki_addon/. Install the result via Anki's
Tools > Add-ons > Install from file...

The Claude Desktop bundle is built separately by mcpb/build.sh.
"""

import json
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "anki_addon"
OUT = ROOT / "dist" / "hypertts_mcp_bridge.ankiaddon"

FILES = ["__init__.py", "config.json", "config.md"]

manifest = {
    # Anki installs into addons21/<package>/. Matches the folder name used
    # for manual installs, so a file install replaces that copy in place.
    "package": "hypertts_mcp_bridge",
    "name": "HyperTTS MCP Bridge",
    # Anki offers an update when the server's time is newer than this, so it
    # must change on every build. AnkiWeb overwrites it with its upload time.
    "mod": int(time.time()),
    "min_point_version": 231000,  # Anki 23.10
    # Cosmetic only: Anki never compares this; it appears in error reports.
    # Keep in step with mcp_server/package.json and mcpb/manifest.json.
    "human_version": "0.1.0",
    "homepage": "https://github.com/bappelt/anki-hypertts-mcp",
}

OUT.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for name in FILES:
        zf.write(SRC / name, name)
    zf.writestr("manifest.json", json.dumps(manifest, indent=4))

print("Built %s" % OUT.relative_to(ROOT))
