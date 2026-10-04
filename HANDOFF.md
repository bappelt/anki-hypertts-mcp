# Handoff: HyperTTS MCP Bridge

Context for picking this project up in Claude Code. Written after an initial
design + prototyping session; nothing below has been tested against a real
Anki install yet.

## Goal

Let an MCP client (Claude, via Claude Code/Desktop) generate audio for a
specific Anki note by triggering an existing **HyperTTS preset** — the same
thing HyperTTS's own "Apply To Notes" button does, just callable from
outside Anki.

Scope is deliberately narrow: one action, "generate audio for note N with
preset P." No voice/service management, no preset editing over MCP — that
stays in HyperTTS's own GUI.

## Why this needed custom code

HyperTTS (AnkiWeb id `111623432`, github.com/Vocab-Apps/anki-hyper-tts) has
no network API of its own — it's a GUI-triggered Anki add-on. AnkiConnect
(the usual Anki-to-MCP bridge) doesn't know about HyperTTS either. So the
only way to drive a HyperTTS preset externally is a small companion Anki
add-on that calls into HyperTTS's own Python internals in-process, then
exposes that over HTTP for an MCP server to call.

**This was verified against real source, not guessed.** HyperTTS's repo was
cloned and read directly (`git clone --depth 1
https://github.com/Vocab-Apps/anki-hyper-tts.git`) to confirm the exact
method names and signatures used below. Pinned to what was on `main` at
clone time — `hypertts_addon/version.py` read `ANKI_HYPER_TTS_VERSION =
'3.6.0'`.

### Key facts confirmed from source

- HyperTTS's repo-root `__init__.py` does `sys.path.insert(0, addon_dir)`
  before `import hypertts_addon` — this makes `hypertts_addon` importable
  as a **top-level module from any other add-on**, without needing to know
  HyperTTS's numeric add-on folder id. Confirmed by reading the file
  directly (`/home/claude/anki-hyper-tts/__init__.py` in the session sandbox).
- `hypertts_addon/__init__.py` assigns `hyper_tts = hypertts.HyperTTS(...)`
  at **module scope** (not inside a function), so after `import
  hypertts_addon`, the live singleton is reachable as `hypertts_addon.hyper_tts`.
- The three calls the bridge relies on, all in `hypertts_addon/hypertts.py`:
  - `hyper_tts.get_preset_list() -> List[PresetInfo(id, name)]`
  - `hyper_tts.load_preset(preset_id) -> BatchConfig`
  - `hyper_tts.process_note_audio(batch, note, add_mode, audio_request_context, text_override, anki_collection) -> (source_text, processed_text, sound_file, full_filename)`
    — this is the exact method that writes the `[sound:...]` tag into the
    field the preset targets (`batch.target.target_field`), matching what
    the GUI's batch-apply flow does (`process_batch_audio` calls the same
    method in a loop).
- `context.AudioRequestContext(constants.AudioRequestReason.batch)` is the
  right context object to pass — mirrors how HyperTTS's own batch code
  constructs it.

**Caveat to carry forward:** these are internal/unpublished APIs. A future
HyperTTS release could rename or restructure them. If the bridge starts
erroring after a HyperTTS update, re-check
`hypertts_addon/hypertts.py` in the currently-installed copy
(`~/.local/share/Anki2/addons21/111623432/hypertts_addon/hypertts.py` on
Linux; standard per-OS Anki2 data dir on Mac/Windows).

### Confirmed NOT the right mechanism: HyperTTS "extensions"

Also cloned `github.com/Vocab-Apps/anki-hyper-tts-extensions` and read a
real example (`services/service_edge_tts.py`). Extensions are single Python
files that HyperTTS itself imports (via its Extensions config tab) to add a
new **TTS service/voice provider** — they import `hypertts_addon.voice`,
`hypertts_addon.service`, etc., and plug into HyperTTS's *service layer*.
They are not separate Anki add-ons (no manifest.json, no independent
loading) and have no relevance to driving HyperTTS from *outside* — that's
what this bridge does instead, on a different axis entirely. Don't submit
this project as a PR into the extensions repo; if publishing, do it as its
own standalone add-on (see "Publishing" below).

## Architecture

```
Claude (MCP client)
   |  MCP tool call
   v
mcp_server/index.js   (Node, stdio MCP server, @modelcontextprotocol/sdk)
   |  HTTP request to 127.0.0.1:8766
   v
anki_addon/            (separate Anki add-on, runs inside Anki's process)
   |  in-process Python call
   v
hypertts_addon.hyper_tts   (HyperTTS's own live singleton)
```

- The Anki add-on runs a `ThreadingHTTPServer` on a background thread
  (started on `profile_did_open`, stopped on `profile_will_close`), bound
  to `127.0.0.1:8766` only. This mirrors AnkiConnect's own well-established
  pattern (persistent local HTTP listener inside Anki) — deliberately a
  different port (`8765` is AnkiConnect's default).
- Two endpoints: `GET /presets`, `POST /generate` (body: `note_id`,
  `preset_id`, optional `text_override`).
- The MCP server resolves a human-readable preset **name** to its id by
  calling `/presets` first, so the MCP tool takes `preset: "My Ukrainian
  Preset"` rather than requiring a UUID.

## Current file layout

```
hypertts-mcp-bridge/
├── README.md              # setup + manual curl test instructions
├── anki_addon/
│   ├── __init__.py         # the HTTP bridge + HyperTTS calls
│   ├── config.json         # host / port / api_key (Anki add-on config)
│   ├── config.md           # config docs shown in Tools > Add-ons > Config
│   └── manifest.json
├── mcp_server/
│   ├── package.json        # depends on @modelcontextprotocol/sdk
│   └── index.js             # list_hypertts_presets, generate_hypertts_audio
└── mcpb/
    ├── manifest.json       # .mcpb bundle manifest (Claude Desktop)
    └── build.sh            # -> dist/hypertts-mcp-bridge.mcpb
```

## What's been verified so far (in the sandbox, not in real Anki)

- `anki_addon/__init__.py` — Python syntax checked (`py_compile`). Cannot
  runtime-test without `aqt`/`anki` installed, which only exist inside a
  real Anki process.
- `mcp_server/index.js` — `npm install`'d against the real
  `@modelcontextprotocol/sdk` package, syntax-checked (`node --check`), and
  smoke-started (`node index.js`) to confirm no import/runtime errors on
  startup. Not tested against a live bridge endpoint (no Anki running in
  the sandbox).

## Open TODOs for Claude Code (has real Anki access, this session didn't)

1. **Real end-to-end test.** Install both add-ons in an actual Anki profile
   with HyperTTS installed, create a preset, and hit `/presets` and
   `/generate` for real via `curl`, then via the MCP server. This is the
   biggest unknown — particularly:
   - Whether calling `hyper_tts.process_note_audio(...)` from our own
     background HTTP-handler thread (rather than from a HyperTTS-managed
     `QueryOp`/`CollectionOp` background thread) causes any Qt/collection
     threading issues. HyperTTS's own batch flow does the equivalent work
     from a background thread too, so this *should* be fine, but hasn't
     been confirmed live.
   - Whether `profile_did_open`/`profile_will_close` is the right hook
     pairing, or whether the server should instead start at add-on load
     time.
2. ~~**Replace hardcoded config with `config.json`.**~~ DONE.
   `host` / `port` / `api_key` now live in `anki_addon/config.json` (+
   `config.md` for the Config UI), read via
   `mw.addonManager.getConfig(__name__)` in `_load_config()` at server
   start. `api_key` defaults to `null` (auth off); when set, requests need
   `X-Api-Key: <value>`, compared with `hmac.compare_digest`. Bad port /
   port-in-use now shows a `showWarning` instead of a traceback.
3. ~~**Graceful failure if HyperTTS isn't installed.**~~ DONE.
   `start_server()` schedules `_warn_if_hypertts_missing()` (~1.2s after
   profile open) which probes `get_hyper_tts()` and, if it fails, prints the
   full reason to the console and shows a terse one-time-per-session
   `showWarning` ("HyperTTS MCP Bridge: the HyperTTS add-on isn't enabled.
   Enable it and restart Anki." - body leads with the add-on name since
   Anki's dialog title isn't always visible).
   The bridge still starts, so `/presets` returns a clear JSON error rather
   than a dead port.
4. **Package as `.ankiaddon`** if you want to install/share it the normal
   way: zip the *contents* of `anki_addon/` (not the folder itself) with a
   `.ankiaddon` extension.
5. ~~**Validate `text_override` client-side.**~~ DONE.
   Checked HyperTTS 3.6.0 source: `text_utils.check_length` is misnamed — it
   only raises `SourceTextEmpty` for blank text and enforces **no maximum**.
   `process_note_audio` *does* hit it (via `process_text`), so blank override
   was already caught (as a 500). Added `_validate_text_override()` in the
   bridge: rejects non-string / blank / over-long overrides with a 400 before
   HyperTTS is touched. Length cap is `max_text_override_chars` in the add-on
   config (default 2000; `0` disables). Unit-tested in isolation.
6. ~~**Package the MCP server for Claude Desktop.**~~ DONE.
   `mcpb/manifest.json` + `mcpb/build.sh` produce
   `dist/hypertts-mcp-bridge.mcpb` (manifest v0.2, stdio node server,
   `user_config` for `bridge_url` / `api_key` -> env vars). Built with
   `npx @anthropic-ai/mcpb pack`; verified two ways: (a) unpacked and drove
   the bundled server over stdio against the live bridge, (b) installed in
   Claude Desktop and exercised the tools in a chat - works. Bundle is
   unsigned (signing is optional, needs a cert). `.mcpb` is
   Claude-Desktop-only; other clients use the stdio server directly (README
   Option B).
7. ~~**Map caller mistakes to HTTP 400.**~~ DONE.
   New `BridgeBadRequest` exception; `generate_audio_for_note()` raises it for
   a missing note id, an unknown preset, and note/preset mismatches (via a
   lazily-resolved allowlist of HyperTTS input-error classes: `PresetNotFound`,
   `SourceFieldNotFoundError`, `TargetFieldNotFoundError`, `FieldNotFoundError`,
   `FieldEmptyError`, `SourceTextEmpty`, `TemplateExpansionError`). The
   `/generate` handler maps `BridgeBadRequest` -> 400; TTS service errors and
   unexpected exceptions still -> 500. Unit-tested in isolation.

## Publishing considerations (deferred, not urgent)

- Structurally this is a normal AnkiWeb-shippable add-on (AnkiConnect is
  the existence proof that "runs a persistent local HTTP server" is an
  accepted pattern).
- If publishing, do it as its own standalone add-on/repo, not a PR into
  `anki-hyper-tts-extensions` (wrong mechanism — see above). Consider
  reaching out to the HyperTTS maintainer first, since it reaches into
  unpublished internals.
- Flag clearly in any README/listing that it depends on HyperTTS internals
  and may break on HyperTTS updates.

## Reference repos (clone these to re-verify against current HyperTTS source)

- `https://github.com/Vocab-Apps/anki-hyper-tts` — HyperTTS itself. Key
  files: `hypertts_addon/hypertts.py` (the `HyperTTS` class),
  `hypertts_addon/__init__.py` (singleton creation), `__init__.py`
  (sys.path setup).
- `https://github.com/Vocab-Apps/anki-hyper-tts-extensions` — the
  "extensions" mechanism, confirmed to be a different, unrelated thing
  (see above). Useful only for context, not for this project's code.
