# HyperTTS MCP Bridge — configuration

Restart Anki after changing any of these.

- **host** — interface the bridge's HTTP server binds to. Keep this at
  `127.0.0.1` (localhost only) unless you have a specific reason not to;
  binding to `0.0.0.0` exposes audio generation to your whole network.
- **port** — TCP port to listen on. Default `8766` (AnkiConnect uses `8765`).
  If another program already holds the port, Anki shows a warning at startup
  and the bridge does not start.
- **api_key** — `null` (default) means no authentication: any local process
  can call the bridge. Set it to a string to require an `X-Api-Key: <value>`
  header on every request; give the same value to the MCP server via the
  `HYPERTTS_BRIDGE_KEY` environment variable. Use a long random value.
- **max_text_override_chars** — cap on the length of a `text_override` sent
  to `/generate` (default `2000`). HyperTTS never limits this itself, so an
  oversized value would go straight to the TTS provider. Set to `0` to
  disable the check.
