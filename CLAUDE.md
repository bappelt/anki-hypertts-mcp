# CLAUDE.md

Read `README.md` (setup, HTTP API) and `DEVELOPMENT.md` (HyperTTS internals,
design decisions, testing, open items) before changing code.

- `anki_addon/__init__.py` calls **unpublished HyperTTS internals**, verified
  against HyperTTS 3.6.0. Before changing those calls, re-read the installed
  HyperTTS source at
  `~/Library/Application Support/Anki2/addons21/111623432/hypertts_addon/hypertts.py`.
- The add-on can't be imported outside Anki (`aqt`/`anki`). Test against a live
  Anki: the bridge is on `127.0.0.1:8766`, AnkiConnect on `127.0.0.1:8765`.
- The installed add-on is a copy at
  `~/Library/Application Support/Anki2/addons21/hypertts_mcp_bridge/`. After
  editing `anki_addon/`, copy the changed files there (or reinstall from
  `python3 build_addon.py`'s output) and restart Anki.
- There is no static `anki_addon/manifest.json`; `build_addon.py` generates
  it. New files in `anki_addon/` must be added to its `FILES` list.
- Real generation overwrites a note field and spends TTS credits. Only run it
  on a throwaway test note (see DEVELOPMENT.md > Testing), never a user's card.
- After changing `mcp_server/` or `mcpb/manifest.json`, rebuild with
  `mcpb/build.sh` and reinstall the `.mcpb` in Claude Desktop.
