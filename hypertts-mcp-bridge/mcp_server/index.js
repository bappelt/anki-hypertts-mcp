#!/usr/bin/env node
/**
 * hypertts-mcp-bridge MCP server
 * ================================
 * Wraps the local Anki add-on's HTTP bridge (see ../anki_addon) as two
 * MCP tools:
 *
 *   - list_hypertts_presets
 *   - generate_hypertts_audio { note_id, preset, text_override? }
 *
 * Requires:
 *   - Anki running, with the HyperTTS add-on and the "HyperTTS MCP Bridge"
 *     add-on both installed and enabled.
 *   - Node 18+ (for global fetch).
 *
 * Configure via env vars:
 *   HYPERTTS_BRIDGE_URL   default: http://127.0.0.1:8766
 *   HYPERTTS_BRIDGE_KEY   optional, sent as X-Api-Key if the add-on's
 *                         BRIDGE_API_KEY is set
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const BRIDGE_URL = process.env.HYPERTTS_BRIDGE_URL || "http://127.0.0.1:8766";
const BRIDGE_KEY = process.env.HYPERTTS_BRIDGE_KEY || null;

function headers() {
  const h = { "Content-Type": "application/json" };
  if (BRIDGE_KEY) h["X-Api-Key"] = BRIDGE_KEY;
  return h;
}

async function bridgeGet(path) {
  const res = await fetch(`${BRIDGE_URL}${path}`, { headers: headers() });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `bridge request failed: ${res.status}`);
  }
  return data;
}

async function bridgePost(path, body) {
  const res = await fetch(`${BRIDGE_URL}${path}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `bridge request failed: ${res.status}`);
  }
  return data;
}

/** Resolve a preset argument that may be an id or a human-readable name. */
async function resolvePresetId(presetArg) {
  const { presets } = await bridgeGet("/presets");
  const byId = presets.find((p) => p.id === presetArg);
  if (byId) return byId;
  const byName = presets.find(
    (p) => p.name.toLowerCase() === String(presetArg).toLowerCase()
  );
  if (byName) return byName;
  const available = presets.map((p) => p.name).join(", ");
  throw new Error(
    `No HyperTTS preset matching "${presetArg}". Available presets: ${available}`
  );
}

const server = new Server(
  { name: "hypertts-mcp-bridge", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "list_hypertts_presets",
      description:
        "List the HyperTTS presets configured in the user's Anki, with id and name.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "generate_hypertts_audio",
      description:
        "Generate audio for a single Anki note using a HyperTTS preset. " +
        "The preset determines the source field/text, the voice/service, and " +
        "the target field the resulting [sound:...] tag is written into.",
      inputSchema: {
        type: "object",
        properties: {
          note_id: {
            type: "integer",
            description: "Anki note id to generate audio for.",
          },
          preset: {
            type: "string",
            description: "HyperTTS preset name or id to use.",
          },
          text_override: {
            type: "string",
            description:
              "Optional: generate audio for this exact text instead of the " +
              "preset's configured source field.",
          },
        },
        required: ["note_id", "preset"],
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "list_hypertts_presets") {
    const { presets } = await bridgeGet("/presets");
    return {
      content: [{ type: "text", text: JSON.stringify(presets, null, 2) }],
    };
  }

  if (name === "generate_hypertts_audio") {
    const preset = await resolvePresetId(args.preset);
    const result = await bridgePost("/generate", {
      note_id: args.note_id,
      preset_id: preset.id,
      text_override: args.text_override,
    });
    return {
      content: [
        {
          type: "text",
          text:
            `Generated audio for note ${result.note_id} using preset "${preset.name}".\n` +
            `Field "${result.target_field}" now contains: ${result.sound_file}\n` +
            `Source text: ${result.source_text}\n` +
            `Processed text: ${result.processed_text}`,
        },
      ],
    };
  }

  throw new Error(`Unknown tool: ${name}`);
});

const transport = new StdioServerTransport();
await server.connect(transport);
