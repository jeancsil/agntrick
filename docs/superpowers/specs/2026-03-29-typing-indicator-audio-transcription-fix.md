# Fix: Typing Indicator & Audio Transcription Restoration

**Date**: 2026-03-29
**Status**: Draft

## Problem Statement

Two features broke during the "Huge refactor" (commit `4a731a9`) when the Python-based WhatsApp integration was replaced with a Go gateway:

1. **Typing indicator stopped working** — Messages are dispatched synchronously, blocking whatsmeow's event loop and preventing `SendChatPresence` from transmitting.
2. **Audio transcription was deleted** — The `AudioTranscriber` class (Groq Whisper API) and audio message handling were removed. Voice messages are silently dropped.

## Root Cause Analysis

### Typing Indicator

In `gateway/session.go`, the `handleEvent` method dispatches messages:

```go
// BROKEN (current — commit 24aafd6):
case *events.Message:
    eh.handleMessage(evt)  // synchronous — blocks event loop

// WORKING (commit ad9d2d8):
case *events.Message:
    go eh.handleMessage(v)  // async — doesn't block event loop
```

The `go` keyword was removed during the "refactor after careful review" commit (`c89a14d`). Without async dispatch:
- `handleMessage` blocks for the entire LLM call duration (90+ seconds)
- whatsmeow's internal event loop is blocked
- `SendChatPresence` calls in the typing goroutine can't transmit because the event loop is occupied

Additionally, all `SendChatPresence` errors are silently discarded with `_ =`.

### Audio Transcription

The Go gateway's `extractMessageText()` only handles text messages (`Conversation` and `ExtendedTextMessage`). Audio messages (`AudioMessage`) return empty string and are silently dropped at `message.go:49` with the log "Message has no text content to process".

The proven `AudioTranscriber` class (~240 lines) from `packages/agntrick-whatsapp/src/agntrick_whatsapp/transcriber.py` was deleted during the refactor.

## Design

### Fix 1: Typing Indicator

The typing indicator sends `ChatPresenceComposing` every 3 seconds via a goroutine.
This refresh loop is essential because WhatsApp auto-expires typing indicators after ~3-5 seconds.
The loop keeps the indicator visible during long LLM processing (90+ seconds).

#### 1.1 Restore async dispatch

File: `gateway/session.go`

Change `handleEvent` to dispatch messages asynchronously:

```go
case *events.Message:
    go eh.handleMessage(evt)
```

Without `go`, `handleMessage` blocks whatsmeow's event loop for the entire LLM call duration.
Even though the typing goroutine runs independently, whatsmeow's internal transport can't send
the presence stanzas when its event loop is blocked.

#### 1.2 Add error logging for SendChatPresence

File: `gateway/message.go`

Replace all `_ = eh.session.SendChatPresence(...)` with proper error logging:

```go
if err := eh.session.SendChatPresence(typingCtx, targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText); err != nil {
    logger.Debug().Err(err).Msg("Failed to send typing indicator")
}
```

#### 1.3 Regression tests

File: `gateway/session_test.go` (extend existing)

Add tests to verify:
- Message events are dispatched via goroutine (not blocking)
- `SendChatPresence` is called with correct parameters during message processing
- Typing indicator starts (initial send) and continues every 3 seconds
- Typing indicator is cleaned up on error and on success
- The 3-second refresh loop fires at least once during a simulated long processing time

These tests prevent the `go` keyword from being silently removed again.

### Fix 2: Audio Transcription

#### Architecture

```
WhatsApp → Go Gateway → Python API → Agent (configured model)
              ↓                            ↑
         Download audio              Transcribe (Groq Whisper)
         Send to API ────────────→  Cache in SQLite → Pass text to agent
```

The Go gateway downloads audio via whatsmeow and sends it to a new Python API endpoint.
The Python side handles transcription (with SQLite caching), then invokes the configured
agent model. The agent receives transcribed text as a regular message — it doesn't need
to know about audio transcription internals, only that it may receive voice message content.

**Model execution**: The agent that processes transcribed audio is the same agent configured
for text messages (default: `assistant` agent using whatever model is configured). No separate
model or agent is needed for audio. The transcription is just text preprocessing before
the agent runs.

#### 2.1 Go Gateway: Audio message detection

File: `gateway/message.go`

Add `extractAudioMessage()` function that:
- Detects `AudioMessage` in the incoming WhatsApp message
- Downloads audio data via whatsmeow's `DownloadAny` or `DownloadMedia` (whatsmeow handles decryption)
- Returns audio bytes, MIME type, and duration

Modify `handleMessage` to try audio extraction when text extraction returns empty:

```go
messageText := extractMessageText(msg)
var audioData []byte
var audioMimeType string

if messageText == "" {
    audioData, audioMimeType, messageText = extractAudioMessage(msg)
    if messageText == "" {
        logger.Warn().Msg("Message has no text or audio content to process")
        return
    }
}
```

When `audioData` is non-empty, call `ForwardAudioMessage` instead of `ForwardMessage`.

#### 2.2 Go Gateway: Forward audio to Python API

File: `gateway/http_client.go`

Add `ForwardAudioMessage` method that:
- Sends multipart form data (audio bytes + metadata) to `/api/v1/channels/whatsapp/audio`
- Returns agent's text response

#### 2.3 Python API: Audio transcription endpoint

File: `src/agntrick/api/routes/whatsapp.py`

Add new endpoint `POST /api/v1/channels/whatsapp/audio` that:
- Receives audio file + metadata (tenant_id, phone, mime_type)
- Computes SHA-256 hash of audio bytes for cache lookup
- Checks `AudioTranscriptionCache` for existing transcription (cache hit)
- On cache miss: saves audio to temp file, calls `AudioTranscriber.transcribe_audio()`
- Stores transcription in cache (keyed by audio hash)
- Passes transcribed text to the configured agent (same as text messages)
- Returns agent response
- Cleans up temp file

The transcribed text is prefixed with `[Voice message]` before being sent to the agent,
so the model knows the input came from a voice message.

#### 2.4 Python: AudioTranscriber service

File: `src/agntrick/services/audio_transcriber.py` (NEW)

Port the proven `AudioTranscriber` class verbatim from
`packages/agntrick-whatsapp/src/agntrick_whatsapp/transcriber.py`. This class:
- Uses Groq's Whisper API (`whisper-large-v3-turbo`)
- Supports `.wav`, `.mp3`, `.ogg`, `.oga`, `.m4a`, `.webm`, `.flac`, `.wma`
- Auto-converts unsupported formats via ffmpeg-python
- Returns error strings (never raises exceptions)
- Reads API key from `GROQ_AUDIO_API_KEY` / `GROQ_API_KEY`

No changes to the class logic — just update the import path.

#### 2.5 Python: AudioTranscriptionCache

File: `src/agntrick/services/audio_transcription_cache.py` (NEW)

SQLite-based cache following the established `YouTubeTranscriptCache` pattern
(`src/agntrick/tools/youtube_cache.py`). Avoids re-transcribing the same audio
when users forward messages to themselves multiple times.

Schema:
```sql
CREATE TABLE IF NOT EXISTS audio_transcription_cache (
    audio_hash TEXT PRIMARY KEY,        -- SHA-256 of audio bytes
    transcription TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    duration_seconds REAL,
    tenant_id TEXT NOT NULL,
    cached_at REAL NOT NULL,
    accessed_at REAL NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_audio_cached_at ON audio_transcription_cache(cached_at);
CREATE INDEX IF NOT EXISTS idx_audio_tenant ON audio_transcription_cache(tenant_id);
```

Features (matching YouTubeTranscriptCache):
- Thread-safe SQLite connections (thread-local storage)
- LRU eviction when cache exceeds size limit (default 100MB)
- Optional TTL-based invalidation (default 30 days)
- Access tracking for analytics
- Per-tenant isolation

Settings:
- Storage: `{STORAGE_DIR}/audio_transcriptions/`
- Max size: 100MB (configurable)
- TTL: 30 days (configurable)

#### 2.6 Python: Audio transcriber tests

File: `tests/test_audio_transcriber.py` (NEW)

Port the proven test suite from the old codebase. Test cases:
- Successful transcription with supported formats
- Format conversion for unsupported formats
- Error handling (missing API key, file not found, oversized file)
- API error responses
- Temp file cleanup

File: `tests/test_audio_transcription_cache.py` (NEW)

Following `YouTubeTranscriptCache` test patterns:
- Cache miss returns None
- Cache set and get round-trip
- Cache hit on same audio hash (deduplication)
- Different audio hashes get different transcriptions
- TTL expiration
- LRU eviction
- Thread safety
- Per-tenant isolation

#### 2.7 Assistant prompt: Audio awareness

File: `src/agntrick/prompts/assistant.md`

Add to `<capabilities>` section:
- The agent receives transcribed audio as `[Voice message] <transcribed text>`
- No special handling needed — the model processes it as regular text
- The model should respond naturally, acknowledging it was a voice message when relevant

## Files Changed

### Go Gateway
| File | Change |
|------|--------|
| `gateway/session.go` | Restore `go eh.handleMessage(evt)` for async dispatch |
| `gateway/message.go` | Add `extractAudioMessage()`, error logging for presence, audio path in `handleMessage` |
| `gateway/http_client.go` | Add `ForwardAudioMessage` method (multipart) |

### Go Tests
| File | Change |
|------|--------|
| `gateway/session_test.go` | Add async dispatch regression test + typing indicator tests |
| `gateway/message_test.go` | Add audio message extraction tests |

### Python
| File | Change |
|------|--------|
| `src/agntrick/services/audio_transcriber.py` | NEW — port proven class from old code |
| `src/agntrick/services/audio_transcription_cache.py` | NEW — SQLite cache (YouTubeTranscriptCache pattern) |
| `src/agntrick/api/routes/whatsapp.py` | Add `/audio` endpoint with cache-first flow |
| `src/agntrick/prompts/assistant.md` | Add voice message awareness |

### Python Tests
| File | Change |
|------|--------|
| `tests/test_audio_transcriber.py` | NEW — port proven test suite |
| `tests/test_audio_transcription_cache.py` | NEW — cache tests (YouTubeTranscriptCache pattern) |
| `tests/test_api/test_whatsapp_route.py` | Add audio endpoint tests |

## Risk Mitigation

- **Typing indicator fix**: Single-line change (`go` keyword) with regression tests that verify the 3-second refresh loop and async dispatch. Low risk.
- **Audio transcription**: Reusing proven code. The `AudioTranscriber` class had 22 passing tests. Porting with minimal changes.
- **Audio caching**: Follows established `YouTubeTranscriptCache` pattern — proven, tested, thread-safe. No reinventing.
- **Model compatibility**: The transcribed text flows as a normal message to whatever model is configured. No model-specific code.
- **No architectural changes**: Both fixes fit within the existing Go gateway + Python API architecture.
- **Backward compatible**: Text message handling is unchanged. Audio is additive.
