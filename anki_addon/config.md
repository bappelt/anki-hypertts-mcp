# HyperTTS MCP Bridge — configuration

Restart Anki after changing any of these.

- **host** — interface the bridge's HTTP server binds to. Keep this at `127.0.0.1` 
- **port** — TCP port to listen on. Default `8766`
- **api_key** — `null` (default) means no authentication: any local program
  can call the bridge. Set it to require an `X-Api-Key` header. Give the same value to the MCP server via the
  `HYPERTTS_BRIDGE_KEY` environment variable.
- **max_text_override_chars** — cap on the length of a `text_override` sent to `/generate` (default `2000`). Set to `0` to disable the check.
