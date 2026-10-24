# HyperTTS MCP Bridge

Lets an MCP client (like Claude) generate audio for an Anki note by calling
an existing **HyperTTS preset** — the same thing the "Apply To Notes" button
does in HyperTTS's GUI, just triggered via MCP instead of a click.

Scope is intentionally narrow: one call, "generate audio for note N with
preset P," writing the `[sound:...]` tag into whatever field that preset is
configured to target. It does **not** expose voice selection, service
config, or preset editing over MCP — manage presets in HyperTTS's own UI as
usual, then drive them remotely.

## How it works

```
+- Claude Desktop ---------------------------------------------------+
|                                                                    |
|  +- HyperTTS MCP Bridge extension (.mcpb) ----------------------+  |
|  |              server/index.js  (Node MCP server)              |  |
|  |            run by Claude Desktop's built-in Node             |  |
|  |                              |                               |  |
|  +------------------------------|-------------------------------+  |
|                                 |                                  |
+---------------------------------|----------------------------------+
                                  |  HTTP to 127.0.0.1:8766
+- Anki --------------------------|----------------------------------+
|                                 |                                  |
|  +- HyperTTS MCP Bridge add-on -|-------------------------------+  |
|  |                              v                               |  |
|  |               hypertts_mcp_bridge/__init__.py                |  |
|  |                   (built from anki_addon/)                   |  |
|  |                              |                               |  |
|  +------------------------------|-------------------------------+  |
|                                 |  in-process Python call          |
|  +- HyperTTS add-on ------------|-------------------------------+  |
|  |                              v                               |  |
|  |                   hypertts_addon.hyper_tts                   |  |
|  |                 (HyperTTS's own live object)                 |  |
|  |                              |                               |  |
|  +------------------------------|-------------------------------+  |
|                                 |                                  |
+---------------------------------|----------------------------------+
                                  |  HTTPS, for most voices
                                  v
                TTS service (Google, ElevenLabs, ...)
```

This shows the Claude Desktop setup. With Claude Code or another MCP client,
the client runs `mcp_server/index.js` directly from this project with your
own Node install instead of from the `.mcpb` bundle.

The bridge add-on calls into HyperTTS directly, doing exactly what
HyperTTS's own "Apply To Notes" button does.

**Compatibility:** tested with HyperTTS 3.7.1. The bridge relies on
HyperTTS internals rather than a public API, so a future HyperTTS update
could break it. If audio generation starts failing after a HyperTTS
update, check for a newer version of this bridge.

Maintainers: see [DEVELOPMENT.md](DEVELOPMENT.md) for which internals are
used and how to re-verify them.

## Setup

### 1. Install the Anki add-on

1. Download `hypertts_mcp_bridge-<version>.ankiaddon` from the
   [latest release](https://github.com/bappelt/anki-hypertts-mcp/releases/latest),
   or build it yourself (needs only Python 3):

   ```bash
   python3 build_addon.py   # writes dist/hypertts_mcp_bridge-<version>.ankiaddon
   ```

2. In Anki: **Tools → Add-ons → Install from file...** and pick that
   `.ankiaddon` file. Reinstalling a newer build the same
   way upgrades it in place and keeps your config.
3. Restart Anki. A tooltip reads
   `HyperTTS MCP Bridge listening on http://127.0.0.1:8766`
   (and the same line prints to the console if you launched Anki from a
   terminal).
4. Make sure HyperTTS itself is installed and enabled — this add-on does
   nothing without it.

Optional: in **Tools → Add-ons → HyperTTS MCP Bridge → Config** (or by
editing the add-on's `config.json`), set `"api_key"` to a string to require
an `X-Api-Key: <value>` header on every request. The same config also holds
`"host"` and `"port"`. Restart Anki after changing it.

### 2. Add the MCP server

Anki must be running (with both add-ons enabled) whenever you use these tools.

#### Option A — Claude Desktop, via the `.mcpb` bundle (recommended)

1. Download `hypertts-mcp-bridge-<version>.mcpb` from the
   [latest release](https://github.com/bappelt/anki-hypertts-mcp/releases/latest),
   or build it yourself (needs Node + network):

   ```bash
   ./mcpb/build.sh          # writes dist/hypertts-mcp-bridge-<version>.mcpb
   ```

2. In Claude Desktop: **Settings → Extensions**, then drag the `.mcpb` file
   in (or double-click it). Claude Desktop ships its own Node runtime, so
   you don't need Node installed to *run* it.
3. In the extension's settings, leave **Bridge URL** at
   `http://127.0.0.1:8766` unless you changed `host`/`port` in the Anki
   add-on config. Fill in **Bridge API key** only if you set `"api_key"`
   there.

#### Option B — any MCP client, via the stdio server directly

```bash
cd mcp_server && npm install
```

Then register it (Claude Desktop's `claude_desktop_config.json`, Claude
Code's `claude mcp add`, etc.), pointing at the absolute path to `index.js`:

```json
{
  "mcpServers": {
    "hypertts-bridge": {
      "command": "node",
      "args": ["/absolute/path/to/anki-hypertts-mcp/mcp_server/index.js"],
      "env": { "HYPERTTS_BRIDGE_KEY": "only-if-you-set-one" }
    }
  }
}
```

`HYPERTTS_BRIDGE_URL` (default `http://127.0.0.1:8766`) and
`HYPERTTS_BRIDGE_KEY` (default none) are the two env vars the server reads.

## Tools exposed

- **`list_hypertts_presets`** — returns each preset's id and name.
- **`generate_hypertts_audio`** — args: `note_id` (required), `preset`
  (required — name or id), `text_override` (optional, generates audio for
  this text instead of the preset's configured source field).

## Manual test (without an MCP client)

With Anki running:

```bash
curl http://127.0.0.1:8766/presets

curl -X POST http://127.0.0.1:8766/generate \
  -H "Content-Type: application/json" \
  -d '{"note_id": 1234567890123, "preset_id": "your-preset-id-from-above"}'
```

Get a real `note_id` from Anki's Browser (right-click a note's row →
"Info", or add a "Note ID" column).

Every response is JSON with an `"ok"` field; failures also carry `"error"`.

| Status | Meaning |
| --- | --- |
| 200 | Success. `/generate` also returns `target_field`, `source_text`, `processed_text`, `sound_file`. |
| 400 | Caller mistake: malformed body, no such note, unknown preset, the note lacks the preset's fields, empty source text, or a `text_override` that is blank or over `max_text_override_chars`. |
| 401 | `api_key` is set and `X-Api-Key` is missing or wrong. |
| 403 | The request came from a web browser (it has an `Origin` header). |
| 404 | Unknown endpoint. |
| 500 | Anything else, such as a TTS service failure or HyperTTS not being enabled. |

## Security

The HTTP server binds to `127.0.0.1` only — nothing outside your machine
can reach it. It also refuses any request carrying an `Origin` header, so
web pages open in your browser can't drive it. It has no built-in rate limiting or write scoping beyond
"generate audio into the field a preset targets," so treat it like
AnkiConnect: fine for local personal use, not something to expose over a
network.
