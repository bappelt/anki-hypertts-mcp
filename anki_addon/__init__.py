"""
HyperTTS MCP Bridge
====================

A small local HTTP bridge that exposes ONE narrow HyperTTS capability:

    "generate audio for note N using preset P, and write the [sound:...]
     tag into the field that preset is configured to target"

It works by importing the already-running HyperTTS add-on's live
`hyper_tts` object in-process (HyperTTS inserts its own package directory
onto sys.path at startup, so `import hypertts_addon` works from any other
add-on without needing to know HyperTTS's numeric add-on id).

This was written against HyperTTS v3.6.0 (github.com/Vocab-Apps/anki-hyper-tts).
The three calls this relies on are:

    hypertts_addon.hyper_tts.get_preset_list()          -> list[PresetInfo(id, name)]
    hypertts_addon.hyper_tts.load_preset(preset_id)      -> BatchConfig
    hypertts_addon.hyper_tts.process_note_audio(...)     -> writes the sound tag,
                                                             returns (source_text,
                                                             processed_text, sound_file,
                                                             full_filename)

If a future HyperTTS release renames/removes these, this bridge will start
raising ImportError/AttributeError with a clear message rather than failing
silently - check hypertts_addon/hypertts.py in your installed copy if that
happens, and update HYPERTTS_HTTP_HANDLERS below.

SECURITY: the server only binds to 127.0.0.1. Set "api_key" in this add-on's
config (Tools > Add-ons > HyperTTS MCP Bridge > Config, or config.json) to a
non-empty string to require an "X-Api-Key: <value>" header on every request.
"""

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anki.errors
import aqt
from aqt import mw
from aqt.utils import showWarning, tooltip

# Fallbacks used only if a key is missing from config.json entirely.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766  # deliberately different from AnkiConnect's default 8765
DEFAULT_MAX_TEXT_OVERRIDE = 2000  # chars; <= 0 in config means "no limit"

# Populated from the add-on config by start_server(); read by BridgeHandler.
_api_key = None            # shared secret, or None to disable auth
_max_text_override = DEFAULT_MAX_TEXT_OVERRIDE  # 0 => unlimited


def _load_config():
    """Read this add-on's config (config.json merged with any user edits from
    Tools > Add-ons > Config) and return a dict of settings.

    Missing/blank values fall back to the module defaults; api_key falls back
    to None (auth disabled).
    """
    cfg = mw.addonManager.getConfig(__name__) or {}
    try:
        port = int(cfg.get("port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    try:
        max_text_override = int(cfg.get("max_text_override_chars", DEFAULT_MAX_TEXT_OVERRIDE))
    except (TypeError, ValueError):
        max_text_override = DEFAULT_MAX_TEXT_OVERRIDE
    return {
        "host": cfg.get("host") or DEFAULT_HOST,
        "port": port,
        "api_key": cfg.get("api_key") or None,
        "max_text_override": max(max_text_override, 0),
    }


def get_hyper_tts():
    """Grab the live HyperTTS singleton from the running HyperTTS add-on.

    Raises RuntimeError with a helpful message if HyperTTS isn't installed
    or hasn't finished loading yet.
    """
    try:
        import hypertts_addon
    except ImportError as e:
        raise RuntimeError(
            "Could not import hypertts_addon - is the HyperTTS add-on "
            "(AnkiWeb id 111623432) installed and enabled?"
        ) from e

    hyper_tts = getattr(hypertts_addon, "hyper_tts", None)
    if hyper_tts is None:
        raise RuntimeError(
            "hypertts_addon.hyper_tts is not set yet - HyperTTS may not "
            "have finished initializing. Try again in a moment."
        )
    return hyper_tts


class BridgeBadRequest(Exception):
    """Raised for a caller mistake (bad note id, unknown preset, note/preset
    mismatch). The /generate handler maps this to HTTP 400; anything else
    coming out of generation is treated as a 500.
    """


# HyperTTS error classes that mean "the request inputs don't line up" rather
# than "something failed on our end" - resolved lazily so a rename in a future
# HyperTTS just drops that entry instead of breaking import.
_CLIENT_INPUT_ERROR_NAMES = (
    "PresetNotFound",
    "SourceFieldNotFoundError",
    "TargetFieldNotFoundError",
    "FieldNotFoundError",
    "FieldEmptyError",
    "SourceTextEmpty",
    "TemplateExpansionError",
)


def _client_input_errors():
    from hypertts_addon import errors

    return tuple(
        cls
        for name in _CLIENT_INPUT_ERROR_NAMES
        if isinstance((cls := getattr(errors, name, None)), type)
    )


def list_presets():
    hyper_tts = get_hyper_tts()
    return [{"id": p.id, "name": p.name} for p in hyper_tts.get_preset_list()]


def _validate_text_override(value):
    """Sanity-check a client-supplied text_override before it reaches HyperTTS.

    Returns the value unchanged (including None, meaning "use the preset's
    source field"). Raises ValueError - which the /generate handler turns into
    a 400 - for a non-string, blank, or over-long override. HyperTTS itself
    only rejects empty text (SourceTextEmpty) and never caps length, so an
    unbounded override would otherwise go straight to the TTS provider.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("text_override must be a string")
    if not value.strip():
        raise ValueError("text_override must not be empty or whitespace")
    if _max_text_override and len(value) > _max_text_override:
        raise ValueError(
            f"text_override is {len(value)} characters; the limit is "
            f"{_max_text_override} (raise max_text_override_chars in the "
            f"add-on config to allow more)"
        )
    return value


def generate_audio_for_note(note_id: int, preset_id: str, text_override=None):
    from hypertts_addon import constants, context

    hyper_tts = get_hyper_tts()

    try:
        note = mw.col.get_note(note_id)
    except anki.errors.NotFoundError:
        # col.get_note() raises rather than returning None for a missing id;
        # turn Anki's alarming "database inconsistent state" text into a plain
        # "no such note" so a bad note_id reads as a client mistake.
        raise BridgeBadRequest(f"No note found with id {note_id}") from None

    try:
        batch = hyper_tts.load_preset(preset_id)
    except _client_input_errors():
        raise BridgeBadRequest(f"No preset found with id {preset_id!r}") from None
    except Exception as e:
        raise RuntimeError(f"Could not load preset '{preset_id}': {e}") from e

    audio_request_context = context.AudioRequestContext(constants.AudioRequestReason.batch)

    try:
        source_text, processed_text, sound_file, full_filename = hyper_tts.process_note_audio(
            batch,
            note,
            add_mode=False,
            audio_request_context=audio_request_context,
            text_override=text_override,
            anki_collection=mw.col,
        )
    except _client_input_errors() as e:
        # e.g. the preset's source/target field isn't on this note, or the
        # resolved source text is empty - the caller paired an incompatible
        # note and preset.
        raise BridgeBadRequest(str(e) or e.__class__.__name__) from e

    return {
        "note_id": note_id,
        "preset_id": preset_id,
        "target_field": batch.target.target_field,
        "source_text": source_text,
        "processed_text": processed_text,
        "sound_file": sound_file,
    }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep Anki's console quiet; remove this to debug

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self):
        if _api_key:
            presented = self.headers.get("X-Api-Key", "")
            # constant-time compare so a wrong key can't be guessed by timing
            if not hmac.compare_digest(presented, _api_key):
                self._send_json(401, {"ok": False, "error": "invalid or missing X-Api-Key"})
                return False
        return True

    def do_GET(self):
        if not self._check_auth():
            return
        if self.path == "/presets":
            try:
                self._send_json(200, {"ok": True, "presets": list_presets()})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        self._send_json(404, {"ok": False, "error": "unknown endpoint"})

    def do_POST(self):
        if not self._check_auth():
            return
        if self.path == "/generate":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                note_id = int(body["note_id"])
                preset_id = body["preset_id"]
                text_override = _validate_text_override(body.get("text_override"))
            except Exception as e:
                self._send_json(400, {"ok": False, "error": f"bad request body: {e}"})
                return

            try:
                result = generate_audio_for_note(note_id, preset_id, text_override)
                self._send_json(200, {"ok": True, **result})
            except BridgeBadRequest as e:
                self._send_json(400, {"ok": False, "error": str(e)})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        self._send_json(404, {"ok": False, "error": "unknown endpoint"})


_server = None
_server_thread = None


def start_server():
    global _server, _server_thread, _api_key, _max_text_override
    if _server is not None:
        return
    cfg = _load_config()
    host, port = cfg["host"], cfg["port"]
    _api_key = cfg["api_key"]
    _max_text_override = cfg["max_text_override"]
    try:
        _server = ThreadingHTTPServer((host, port), BridgeHandler)
    except OSError as e:
        _server = None
        showWarning(
            f"HyperTTS MCP Bridge could not start its HTTP server on "
            f"{host}:{port}:\n\n{e}\n\n"
            f"Another program may already be using that port. Change "
            f'"port" in this add-on\'s config and restart Anki.',
            title="HyperTTS MCP Bridge",
        )
        return
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    auth_note = " (X-Api-Key required)" if _api_key else ""
    msg = f"listening on http://{host}:{port}{auth_note}"
    # print() only shows when Anki was launched from a terminal; the tooltip
    # is what a normal GUI launch actually sees. Defer it so it lands after
    # the profile-open UI churn (otherwise it can flash past).
    print(f"[hypertts-mcp-bridge] {msg}")
    mw.progress.single_shot(
        800, lambda: tooltip(f"HyperTTS MCP Bridge {msg}", period=2000), False
    )
    # HyperTTS creates its singleton at add-on import time, so by now it should
    # be reachable; if it isn't, tell the user up front instead of letting the
    # first MCP call be the thing that discovers HyperTTS is missing.
    mw.progress.single_shot(1200, _warn_if_hypertts_missing, False)


_hypertts_warning_shown = False


def _warn_if_hypertts_missing():
    """Startup check: is HyperTTS importable and initialized? If not, warn once
    per session. The bridge stays up (so /presets still returns a clear JSON
    error), but requests can't work until HyperTTS is installed/enabled and
    Anki is restarted.
    """
    global _hypertts_warning_shown
    try:
        get_hyper_tts()
        return  # all good
    except Exception as e:
        reason = str(e) or repr(e)
    # full reason goes to the console; the dialog stays terse
    print(f"[hypertts-mcp-bridge] HyperTTS not available: {reason}")
    if _hypertts_warning_shown:
        return
    _hypertts_warning_shown = True
    showWarning(
        "HyperTTS MCP Bridge: the HyperTTS add-on isn't enabled. "
        "Enable it and restart Anki.",
        title="HyperTTS MCP Bridge",
    )


def stop_server():
    global _server, _server_thread
    if _server is not None:
        _server.shutdown()
        _server = None
        _server_thread = None


def on_profile_open():
    start_server()


def on_profile_close():
    stop_server()


aqt.gui_hooks.profile_did_open.append(on_profile_open)
aqt.gui_hooks.profile_will_close.append(on_profile_close)
