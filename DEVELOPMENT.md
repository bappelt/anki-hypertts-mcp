# Development notes

Maintainer-facing background for the HyperTTS MCP Bridge. For installing and
using it, see [README.md](README.md).

## Why this needs custom code

HyperTTS (AnkiWeb id `111623432`, <https://github.com/Vocab-Apps/anki-hyper-tts>)
has no network API of its own. It is a GUI-triggered Anki add-on, and
AnkiConnect doesn't know about it either. The only way to drive a HyperTTS
preset from outside Anki is a companion add-on that calls HyperTTS's Python
internals in-process and exposes that over HTTP. That is what `anki_addon/`
does; `mcp_server/` wraps the HTTP bridge as MCP tools.

Scope is deliberately narrow: one action, "generate audio for note N with
preset P." Voice/service management and preset editing stay in HyperTTS's own
GUI.

## The HyperTTS internals we depend on

These are **internal, unpublished APIs**. They were verified by reading
HyperTTS's source at version **3.6.0** (`hypertts_addon/version.py`:
`ANKI_HYPER_TTS_VERSION = '3.6.0'`), not guessed.

- HyperTTS's repo-root `__init__.py` does `sys.path.insert(0, addon_dir)`
  before `import hypertts_addon`. That makes `hypertts_addon` importable as a
  top-level module from any other add-on, without knowing HyperTTS's numeric
  add-on folder id.
- `hypertts_addon/__init__.py` assigns `hyper_tts = hypertts.HyperTTS(...)` at
  **module scope**, so the live singleton is `hypertts_addon.hyper_tts`.
- The three calls the bridge uses, all in `hypertts_addon/hypertts.py`:
  - `hyper_tts.get_preset_list() -> List[PresetInfo(id, name)]`
  - `hyper_tts.load_preset(preset_id) -> BatchConfig`
  - `hyper_tts.process_note_audio(batch, note, add_mode, audio_request_context, text_override, anki_collection) -> (source_text, processed_text, sound_file, full_filename)`.
    This writes the `[sound:...]` tag into `batch.target.target_field`. It is
    the same method HyperTTS's own "Apply To Notes" flow calls in a loop
    (`process_batch_audio`).
- `context.AudioRequestContext(constants.AudioRequestReason.batch)` is the
  context object to pass, mirroring HyperTTS's own batch code.
- `text_utils.check_length` is misnamed: it only raises `SourceTextEmpty` for
  blank text and enforces **no maximum length**. That is why the bridge caps
  `text_override` itself (`max_text_override_chars`).
- Error classes in `hypertts_addon/errors.py` that the bridge treats as caller
  mistakes (HTTP 400): `PresetNotFound`, `SourceFieldNotFoundError`,
  `TargetFieldNotFoundError`, `FieldNotFoundError`, `FieldEmptyError`,
  `SourceTextEmpty`, `TemplateExpansionError`. They are resolved lazily by
  name, so a rename in a future HyperTTS drops that entry (it becomes a 500)
  instead of breaking import.

### When HyperTTS updates

If the bridge starts erroring after a HyperTTS update, open the installed
`hypertts_addon/hypertts.py` and check whether the three methods above changed
shape, then adjust `anki_addon/__init__.py`. Installed locations:

- macOS: `~/Library/Application Support/Anki2/addons21/111623432/`
- Linux: `~/.local/share/Anki2/addons21/111623432/`
- Windows: `%APPDATA%\Anki2\addons21\111623432\`

To re-verify against upstream:

```bash
git clone --depth 1 https://github.com/Vocab-Apps/anki-hyper-tts.git
```

Key files: `__init__.py` (sys.path setup), `hypertts_addon/__init__.py`
(singleton), `hypertts_addon/hypertts.py` (the `HyperTTS` class),
`hypertts_addon/errors.py`.

### Not the right mechanism: HyperTTS "extensions"

<https://github.com/Vocab-Apps/anki-hyper-tts-extensions> holds single Python
files that HyperTTS imports (via its Extensions config tab) to add a new
**TTS service/voice provider**. They plug into HyperTTS's service layer and
are not standalone add-ons. They have nothing to do with driving HyperTTS
from outside, so this project should not be submitted there.

## Design decisions

- **Persistent local HTTP server inside Anki**, the same pattern AnkiConnect
  uses. A `ThreadingHTTPServer` runs on a daemon thread, bound to
  `127.0.0.1:8766` by default. Port 8766 is chosen to avoid AnkiConnect's
  8765.
- **Lifecycle hooks:** started on `profile_did_open`, stopped on
  `profile_will_close`, so the server only runs while a collection is open.
- **Threading:** `process_note_audio` runs on the HTTP handler's thread, not
  Anki's main thread or a HyperTTS-managed `QueryOp`. HyperTTS's own batch
  flow also does this work off the main thread. Verified live on 2026-10-04:
  three concurrent `/generate` calls on the same note all succeeded and left
  exactly one sound tag. It has not been stress-tested beyond that.
- **Preset by name:** the MCP server resolves a preset name to its id by
  calling `/presets` first, so tool callers can say `"Basic Ukrainian"`
  instead of a UUID.
- **HyperTTS missing:** the bridge still starts, and ~1.2 s after profile
  open it warns once per session if HyperTTS can't be imported. `/presets`
  then returns a JSON error rather than a dead port.

## Testing

There is no automated test suite. The add-on imports `aqt`/`anki`, which only
exist inside a running Anki, so testing is manual against a live Anki.

### Live test procedure

1. Install the add-on into Anki with HyperTTS installed (see README), and
   start Anki. For quick iteration, copying `anki_addon/`'s files into
   `addons21/hypertts_mcp_bridge/` and restarting also works.
2. Exercise the bridge with the curl commands in the README, including the
   error paths: unknown note id, blank `text_override`, missing `note_id`.
   Each should return 400 with a readable message.
3. Drive the MCP server over stdio from `mcp_server/`:

   ```bash
   { printf '%s\n' \
     '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' \
     '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
     '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_hypertts_presets","arguments":{}}}'; \
     sleep 3; } | node index.js
   ```

4. For a real generation, use a throwaway note in a throwaway deck so no real
   card's field is overwritten. If AnkiConnect is installed, a test note can
   be created without the GUI:

   ```bash
   curl -s localhost:8765 -d '{"action":"addNote","version":6,"params":{"note":{"deckName":"HyperTTS Bridge Test","modelName":"Basic+","fields":{"English":"thank you","Ukrainian":"дякую"},"tags":["hypertts-bridge-test"]}}}'
   ```

   The note type must have the preset's source and target fields. Delete the
   deck afterwards, then run Tools > Check Media to clear the orphaned audio.

### Test history

- 2026-08-30: `.mcpb` bundle installed in Claude Desktop and both tools
  exercised in chat.
- 2026-10-04: full live pass on macOS, HyperTTS 3.6.0. All endpoints and
  error paths behaved as documented. Generation succeeded via the MCP tool
  with two different presets (one ElevenLabs), and 20 concurrent `/presets`
  plus 3 concurrent `/generate` calls succeeded.

## Packaging

- **Claude Desktop bundle:** `./mcpb/build.sh` stages `manifest.json` plus the
  server with lockfile-exact production `node_modules`, validates, and packs
  to `dist/hypertts-mcp-bridge.mcpb`. The bundle is unsigned; signing is
  optional and needs a certificate. `.mcpb` is Claude-Desktop-only; other
  clients run `mcp_server/index.js` directly.
- **Anki add-on:** `python3 build_addon.py` writes
  `dist/hypertts_mcp_bridge.ankiaddon`, following the pattern of
  [anki-quick-image-search](https://github.com/bappelt/anki-quick-image-search).
  It zips the files listed in `FILES` and generates `manifest.json` at build
  time, so there is no static manifest in `anki_addon/`. Things to know:
  - `package` is required for file installs and becomes the folder name
    under `addons21/`. It is `hypertts_mcp_bridge`, matching the manual
    install folder, so a file install replaces that copy in place.
  - Anki offers an update only when the server's time is newer than the
    installed `mod`, so `mod` is stamped with the build time. AnkiWeb
    overwrites it with its own upload time.
  - `human_version` is never compared by Anki; it only shows in error
    reports. Keep it in step with `mcp_server/package.json` and
    `mcpb/manifest.json`.
  - The manifest was validated against the `_manifest_schema` in the
    installed Anki's `aqt/addons.py`. Unknown keys are silently dropped.
  - Adding a new file to `anki_addon/` means adding it to `FILES`.

## Open items

- MCP server: report a friendly "is Anki running?" message when the bridge
  is unreachable, instead of a raw fetch error.
- MCP server: return tool failures as results with `isError: true` rather
  than throwing JSON-RPC errors.

## Publishing considerations (deferred)

- Structurally this is a normal AnkiWeb-shippable add-on; AnkiConnect shows
  a persistent local HTTP server is an accepted pattern.
- Publish as its own standalone add-on/repo, not into the extensions repo.
- Consider contacting the HyperTTS maintainer first, since this reaches into
  unpublished internals.
- State clearly in any listing that it depends on HyperTTS internals and may
  break on HyperTTS updates.
