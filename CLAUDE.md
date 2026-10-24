# CLAUDE.md

Read `README.md` (setup, HTTP API) and `DEVELOPMENT.md` (HyperTTS internals,
design decisions, testing, open items) before changing code.

- `anki_addon/__init__.py` calls **unpublished HyperTTS internals**, verified
  against HyperTTS 3.7.1. Before changing those calls, re-read the installed
  HyperTTS source, `addons21/111623432/hypertts_addon/hypertts.py` in Anki's
  data folder (DEVELOPMENT.md lists it per OS).
- The add-on can't be imported outside Anki (`aqt`/`anki`). Test against a live
  Anki: the bridge is on `127.0.0.1:8766`, AnkiConnect on `127.0.0.1:8765`.
- To test changes to `anki_addon/`, copy the changed files into the installed
  bridge's folder under `addons21/` and restart Anki. Check which folder
  exists: `1885999094` for an AnkiWeb install (the next AnkiWeb update
  overwrites local changes), `hypertts_mcp_bridge` for one installed from a
  file. Installing `build_addon.py`'s output alongside an AnkiWeb install adds
  a second bridge competing for the same port.
- There is no static `anki_addon/manifest.json`; `build_addon.py` generates
  it. New files in `anki_addon/` must be added to its `FILES` list.
- Real generation overwrites a note field and spends TTS credits. Only run it
  on a throwaway test note (see DEVELOPMENT.md > Testing), never a user's card.
- When a change is visible to users, add an entry under `## [Unreleased]` in
  `CHANGELOG.md` in the same commit. Skip CI, refactors and maintainer docs.
- The version lives only in `mcp_server/package.json`; builds and the server
  read it from there. Don't hard-code versions elsewhere. To release, follow
  DEVELOPMENT.md > Releasing.
- After changing `mcp_server/` or `mcpb/manifest.json`, rebuild with
  `mcpb/build.sh` and reinstall the `.mcpb` in Claude Desktop.
