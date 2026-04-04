# Typing Indicator & Audio Transcription Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Use `glm-4.7` for all subagent dispatching** (implementer, reviewers, unless a task specifically requires more capable reasoning — then escalate to `glm-5.1` for that task only).

**Goal:** Fix the typing indicator (restore async dispatch) and restore audio transcription with Groq Whisper + SQLite caching.

**Architecture:** Minimal changes to Go gateway (restore `go` keyword, add audio download). Python side ports proven AudioTranscriber class and new SQLite cache following YouTubeTranscriptCache pattern.

**Tech Stack:** Go (whatsmeow), Python (FastAPI, httpx, SQLite), Groq Whisper API

**Spec:** `docs/superpowers/specs/2026-03-29-typing-indicator-audio-transcription-fix.md`

---

## Phase 1: Typing Indicator Fix

### Task 1: Restore async message dispatch in Go gateway

**Files:**
- Modify: `gateway/session.go:207-220`

- [ ] **Step 1: Write the failing test for async dispatch**

Add to `gateway/session_test.go`:

```go
func TestHandleEvent_DispatchesMessageAsynchronously(t *testing.T) {
    // Verify that handleEvent dispatches Message events via goroutine
    // by checking that the method returns immediately without blocking

    mockClient := &whatsmeow.Client{}
    mockManager := &SessionManager{
        config:  &Config{},
        clients: make(map[string]*whatsmeow.Client),
        handlers: make(map[string]*EventHandler),
        containers: make(map[string]*sqlstore.Container),
        logger: zerolog.Nop(),
        httpClient: &HTTPClient{},
    }

    handler := &EventHandler{
        tenantID: "test-tenant",
        session:  mockClient,
        manager:  mockManager,
        logger:  zerolog.Nop(),
    }

    // Record when handleMessage is called
    var handleMessageCalled bool
    var handleMessageDone chan struct{}

    // Store original handleMessage
    originalHandleMessage := handleMessage

    handleMessage = func(eh *EventHandler, msg *events.Message) {
        handleMessageCalled = true
        originalHandleMessage(eh, msg)
        close(handleMessageDone)
    }

    // Create a message event
    msg := &events.Message{
        Info: types.MessageInfo{
            Chat:      types.JID{User: "1234567890", Server: "s.whatsapp.net"},
            Sender:    types.JID{User: "1234567890", Server: "s.whatsapp.net"},
            IsFromMe: true,
            Timestamp: time.Now(),
            ID:      "msg-123",
        },
        Message: &waE2E.Message{
            Conversation: proto.String("hello"),
        },
    }

    // Call handleEvent
    start := time.Now()
    handler.handleEvent(msg)
    elapsed := time.Since(start)

    // handleEvent should return immediately (not block for LLM call)
    assert elapsed < 100*time.Millisecond, "handleEvent blocked — message not dispatched asynchronously"

    // Wait for handleMessage to be called
    select {
    case <-handleMessageDone:
        case <-time.After(2 * time.Second):
            t.Fatal("handleMessage was not called within timeout")
    }
    assert handleMessageCalled, "handleMessage was not dispatched")
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gateway && go test -run TestHandleEvent_DispatchesMessageAsynchronously -v`
Expected: FAIL — handleEvent currently calls handleMessage synchronously (missing `go` keyword)

Note: This test should fail because the current code calls `eh.handleMessage(evt)` without `go`, which blocks.

- [ ] **Step 3: Fix session.go to restore async dispatch**

In `gateway/session.go`, change line 214:
```go
// FROM (broken):
case *events.Message:
    eh.handleMessage(evt)

// TO (fixed):
case *events.Message:
    go eh.handleMessage(evt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd gateway && go test -run TestHandleEvent_DispatchesMessageAsynchronously -v`
Expected: PASS

Note: handleEvent returns immediately because handleMessage runs in a goroutine.

- [ ] **Step 5: Commit**

```bash
git add gateway/session.go gateway/session_test.go
git commit -m "fix(gateway): restore async message dispatch for typing indicator"
```

### Task 2: Add error logging for SendChatPresence

**Files:**
- Modify: `gateway/message.go:69,74,94,104`

- [ ] **Step 1: Replace silenced errors with proper logging**

In `gateway/message.go`, replace all `_ = eh.session.SendChatPresence(...)` with error logging:

Change line 69:
```go
// FROM:
_ = eh.session.SendChatPresence(typingCtx, targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText)
// TO:
if err := eh.session.SendChatPresence(typingCtx, targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText); err != nil {
    logger.Debug().Err(err).Msg("Failed to send composing presence")
}
```

Change line 74:
```go
// FROM:
_ = eh.session.SendChatPresence(typingCtx, targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText)
// TO:
if err := eh.session.SendChatPresence(typingCtx, targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText); err != nil {
    logger.Debug().Err(err).Msg("Failed to send composing presence (tick)")
}
```

Change line 94:
```go
// FROM:
_ = eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText)
// TO:
if err := eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText); err != nil {
    logger.Debug().Err(err).Msg("Failed to clear typing indicator")
}
```

Change line 104:
```go
// FROM:
_ = eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText)
// TO:
if err := eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText); err != nil {
    logger.Debug().Err(err).Msg("Failed to clear typing indicator (completion)")
}
```

- [ ] **Step 2: Run Go tests**

Run: `cd gateway && go test ./... -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add gateway/message.go
git commit -m "fix(gateway): add error logging for SendChatPresence calls"
```

---

## Phase 2: Audio Transcription — Python Side

### Task 3: Port AudioTranscriber service from proven code
**Files:**
- Create: `src/agntrick/services/__init__.py`
- Create: `src/agntrick/services/audio_transcriber.py`

- [ ] **Step 1: Create services directory init file**

Create `src/agntrick/services/__init__.py`:
```python
"""Agntrick services package."""
```

- [ ] **Step 2: Port AudioTranscriber from old proven code**

Create `src/agntrick/services/audio_transcriber.py` by copying the proven class from the old commit `591670a^:packages/agntrick-whatsapp/src/agntrick_whatsapp/transcriber.py` (available in git history at commit `591670a`).

Key changes from the old version:
- Update docstring module path references from `agntrick.services.audio_transcriber`
- Keep all class logic identical
- Keep `GROQ_AUDIO_API_KEY` / `GROQ_API_KEY` / `GROQ_WHISPER_MODEL` env var support
- Keep `ffmpeg-python` conversion logic
- Keep error-as-string pattern (never raise exceptions)
- Keep `httpx.AsyncClient` for API calls
- Keep `_SUPPORTED_FORMATS`, `_AVAILABLE_MODELS`, `_DEFAULT_MODEL`, `_API_URL`, `_MAX_SIZE_MB`, `_MP3_BITRATE` constants
- Keep `_load_config()`, `_validate_path()`, `_convert_to_mp3()` methods
- Keep `transcribe_audio()` main method
- Keep `get_available_models()`, `create_default` class methods
- Remove `yaml` config file loading (use env vars directly instead — simpler)
- Keep `is_configured` property

The - [ ] **Step 3: Run Go tests to verify no compilation issues**

Run: `cd gateway && go vet ./... -v`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/services/__init__.py src/agntrick/services/audio_transcriber.py
git commit -m "feat: port AudioTranscriber service from proven WhatsApp code"
```
### Task 4: Create AudioTranscriptionCache
**Files:**
- Create: `src/agntrick/services/audio_transcription_cache.py`
- Create: `tests/test_audio_transcription_cache.py`

- [ ] **Step 1: Write the cache implementation**

Create `src/agntrick/services/audio_transcription_cache.py` following the `YouTubeTranscriptCache` pattern from `src/agntrick/tools/youtube_cache.py`:

Schema:
```sql
CREATE TABLE IF NOT EXISTS audio_transcription_cache (
    audio_hash TEXT PRIMARY KEY,
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

Features (matching YouTubeTranscriptCache exactly):
- Thread-safe SQLite connections using thread-local storage
- LRU eviction when cache exceeds size limit (100MB default)
- TTL-based invalidation (30 days default)
- Access tracking
- Per-tenant isolation
- `get(audio_hash, tenant_id)` → returns cached transcription or- [ ] **Step 2: Write cache tests**

Create `tests/test_audio_transcription_cache.py`:
```python
"""Tests for AudioTranscriptionCache."""
import hashlib
import time

import pytest

from agntrick.services.audio_transcription_cache import AudioTranscriptionCache


@pytest.fixture
def cache(tmp_path):
    return AudioTranscriptionCache(cache_dir=tmp_path, max_size_mb=10, ttl_days=30)


class TestAudioTranscriptionCache:
    def test_cache_miss_returns_none(self, cache):
        result = cache.get("nonexistent_hash", "tenant1")
        assert result is None

    def test_set_and_get_roundtrip(self, cache):
        audio_hash = hashlib.sha256(b"fake audio data").hexdigest()
        cache.set(
            audio_hash=audio_hash,
            transcription="Hello world",
            mime_type="audio/ogg",
            tenant_id="tenant1",
            duration_seconds=5.0,
        )
        result = cache.get(audio_hash, "tenant1")
        assert result is not None
        assert result["transcription"] == "Hello world"

    def test_same_hash_deduplicated(self, cache):
        audio_hash = hashlib.sha256(b"same audio").hexdigest()
        cache.set(audio_hash=audio_hash, transcription="First", mime_type="audio/ogg", tenant_id="t1")
        cache.set(audio_hash=audio_hash, transcription="First", mime_type="audio/ogg", tenant_id="t1")
        result = cache.get(audio_hash, "t1")
        assert result["access_count"] == 2

    def test_different_hashes_different_transcriptions(self, cache):
        h1 = hashlib.sha256(b"audio one").hexdigest()
        h2 = hashlib.sha256(b"audio two").hexdigest()
        cache.set(audio_hash=h1, transcription="One", mime_type="audio/ogg", tenant_id="t1")
        cache.set(audio_hash=h2, transcription="Two", mime_type="audio/ogg", tenant_id="t1")
        assert cache.get(h1, "t1")["transcription"] == "One"
        assert cache.get(h2, "t1")["transcription"] == "Two"

    def test_per_tenant_isolation(self, cache):
        audio_hash = hashlib.sha256(b"shared audio").hexdigest()
        cache.set(audio_hash=audio_hash, transcription="For tenant1", mime_type="audio/ogg", tenant_id="t1")
        cache.set(audio_hash=audio_hash, transcription="For tenant2", mime_type="audio/ogg", tenant_id="t2")
        # Same hash, different tenant — each gets own entry
        assert cache.get(audio_hash, "t1")["transcription"] == "For tenant1"
        assert cache.get(audio_hash, "t2")["transcription"] == "For tenant2"

    def test_ttl_expiration(self, tmp_path):
        cache = AudioTranscriptionCache(cache_dir=tmp_path, ttl_days=0)
        audio_hash = hashlib.sha256(b"expired audio").hexdigest()
        cache.set(audio_hash=audio_hash, transcription="Old", mime_type="audio/ogg", tenant_id="t1")
        # Manually expire by updating cached_at to past
        conn = cache._get_connection()
        conn.execute("UPDATE audio_transcription_cache SET cached_at = ? WHERE audio_hash = ?", (time.time() - 100,))
        conn.commit()
        result = cache.get(audio_hash, "t1")
        assert result is None
```

- [ ] **Step 3: Run cache tests**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_audio_transcription_cache.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/services/audio_transcription_cache.py tests/test_audio_transcription_cache.py
git commit -m "feat: add AudioTranscriptionCache with SQLite backend"
```
### Task 5: Port AudioTranscriber tests from proven code
**Files:**
- Create: `tests/test_audio_transcriber.py`

- [ ] **Step 1: Port test suite from old proven code**

Create `tests/test_audio_transcriber.py` by adapting the test suite from the old commit `7ec0691` (available via `git show 7ec0691:agentic-framework/tests/test_audio_transcriber.py`).

Key changes:
- Update import to `from agntrick.services.audio_transcriber import AudioTranscriber`
- Keep all 22 test cases
- Mock `httpx.AsyncClient` for API calls
- Mock `ffmpeg` for format conversion tests
- Use `monkeypatch` for environment variable manipulation (following project's test pattern)

Test cases to port:
1. `test_transcribe_audio_success` - successful transcription
2. `test_transcribe_audio_no_api_key` - missing API key error
3. `test_transcribe_audio_file_not_found` - file not found error
4. `test_transcribe_audio_unsupported_format_conversion` - format conversion
5. `test_transcribe_audio_oversized_file` - file size limit
6. `test_transcribe_audio_api_error` - API error handling
7. `test_transcribe_audio_timeout` - timeout handling
8. `test_is_configured_with_key` - configuration check
9. `test_is_configured_without_key` - missing key check
10. `test_get_available_models` - model list
11. `test_create_default` - factory method
12. `test_validate_path_valid` - path validation success
13. `test_validate_path_not_found` - path not found
14. `test_validate_path_is_directory` - path is directory
15. `test_convert_to_mp3_success` - successful conversion
16. `test_convert_to_mp3_import_error` - ffmpeg not installed
17. `test_convert_to_mp3_conversion_error` - conversion failure
18. `test_load_config_from_file` - YAML config loading
19. `test_load_config_missing_file` - missing config file
20. `test_transcribe_empty_result` - empty transcription
21. `test_transcribe_unexpected_response` - unexpected API response
22. `test_temp_file_cleanup` - temp file cleanup

- [ ] **Step 2: Run transcriber tests**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_audio_transcriber.py -v`
Expected: All 22 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_audio_transcriber.py
git commit -m "test: add AudioTranscriber tests ported from proven code"
```
---

## Phase 3: Audio Transcription — Go Gateway
### Task 6: Add audio message detection in Go gateway
**Files:**
- Modify: `gateway/message.go:200-221`
- Modify: `gateway/message.go:46-55`

- [ ] **Step 1: Add extractAudioMessage function**

Add to `gateway/message.go` after `extractMessageText`:

```go
// extractAudioMessage detects and downloads audio messages.
// whatsmeow handles decryption automatically via DownloadAny/DownloadMedia.
// Returns audio bytes, MIME type, and a placeholder message.
// If the message has no audio or download fails, returns nil bytes.
func extractAudioMessage(msg *events.Message) (audioData []byte, mimeType string, err error) {
	if msg.Message == nil {
		return nil, "", "", nil
	}

	audioMsg := msg.Message.GetAudioMessage()
	if audioMsg == nil {
		return nil, "", "", fmt.Errorf("no audio message")
	}

	// Get MIME type and duration
	mimeType = audioMsg.GetMimetype()
	if mimeType == "" {
		mimeType = "audio/ogg" // WhatsApp default for voice messages
	}

	// Download audio data (whatsmeow handles decryption)
	audioData, err = msg.DownloadAudio()
	if err != nil {
		return nil, "", "", fmt.Errorf("failed to download audio: %w", err)
	}

	return audioData, mimeType, nil
}
```

- [ ] **Step 2: Modify handleMessage to try audio extraction**

In `gateway/message.go`, replace lines 48-52:
```go
// FROM:
	// Extract message text
	messageText := extractMessageText(msg)
	if messageText == "" {
		logger.Warn().Msg("Message has no text content to process")
		return
	}
// TO:
	// Extract message text
	messageText := extractMessageText(msg)
	var audioData []byte
	var audioMimeType string

	if messageText == "" {
		// Try audio message extraction
		audioData, audioMimeType, messageText = extractAudioMessage(msg)
		if messageText == "" {
			logger.Warn().Msg("Message has no text or audio content to process")
			return
		}
	}
```

Also update `forwardToPythonAPI` call to handle audio:
```go
// FROM:
	response, err := forwardToPythonAPI(eh, messageText, logger)
// TO:
	var response string
	var err error
	if len(audioData) > 0 {
		response, err = forwardAudioToPythonAPI(eh, audioData, audioMimeType, logger)
	} else {
		response, err = forwardToPythonAPI(eh, messageText, logger)
	}
```

- [ ] **Step 3: Add forwardAudioToPythonAPI to http_client.go**

Add to `gateway/http_client.go`:
```go
// ForwardAudioMessage sends audio data to the Python API for transcription and agent processing.
// The Python API handles: transcription (Groq Whisper), caching (SQLite), and agent invocation.
func (c *HTTPClient) ForwardAudioMessage(tenantID string, phone string, audioData []byte, mimeType string) (string, error) {
	url := fmt.Sprintf("%s/api/v1/channels/whatsapp/audio", c.baseURL)

	// Build multipart form
	var buf bytes.Buffer
	writer := multipart.NewWriter(&buf)

	// Add audio file
	part, err := writer.CreateFormFile("audio", "voice_message.ogg")
	if err != nil {
		return "", fmt.Errorf("failed to create multipart form: %w", err)
	}
	if _, err := part.Write(audioData); err != nil {
		return "", fmt.Errorf("failed to write audio data: %w", err)
	}

	// Add metadata fields
	_ = writer.WriteField("tenant_id", tenantID)
	_ = writer.WriteField("phone", phone)
	_ = writer.WriteField("mime_type", mimeType)
	writer.Close()

	req, err := http.NewRequest("POST", url, &buf)
	if err != nil {
		return "", fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", writer.FormDataContentType())
	if c.apiKey != "" {
		req.Header.Set("X-API-Key", c.apiKey)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unexpected status code %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read response body: %w", err)
	}

	var apiResp apiResponse
	if err := json.Unmarshal(body, &apiResp); err != nil {
		return "", fmt.Errorf("failed to parse API response: %w", err)
	}

	if apiResp.Response == "" {
		return "", fmt.Errorf("empty response from API")
	}

	return apiResp.Response, nil
}
```

Add import `"mime/multipart"` to `http_client.go` imports.

- [ ] **Step 4: Run Go tests**

Run: `cd gateway && go test ./... -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/message.go gateway/http_client.go
git commit -m "feat(gateway): add audio message detection and forwarding"
```
---

## Phase 4: Audio Transcription — Python API
### Task 7: Add audio transcription endpoint
**Files:**
- Modify: `src/agntrick/api/routes/whatsapp.py:282-398`
- Create: `tests/test_api/test_audio_route.py`

- [ ] **Step 1: Add audio message endpoint**

Add to `src/agntrick/api/routes/whatsapp.py` after the existing `whatsapp_webhook` endpoint:
```python
class AudioMessageRequest(BaseModel):
    """Request model for audio message transcription."""
    tenant_id: str
    phone: str
    mime_type: str = "audio/ogg"


    duration_seconds: float | None = None
@channels_router.post("/whatsapp/audio")
async def whatsapp_audio_webhook(
    request: Request, registry: WhatsAppRegistry = Depends(get_whatsapp_registry)
) -> dict[str, str]:
    """Receive audio message from Go gateway, transcribe and process with agent.
    Args:
        request: The FastAPI request containing audio data.
        registry: WhatsApp registry instance.
    Returns:
        Agent response with tenant_id.
    Raises:
        HTTPException: If authentication fails or processing fails.
    """
    logger = logging.getLogger(__name__)

    # Check API key
    api_key = request.headers.get("X-API-Key")
    config = get_config()
    if not api_key or api_key not in config.auth.api_keys:
        logger.warning("Invalid API key attempted for WhatsApp audio webhook")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Parse multipart form
    form = await request.form()
    audio_file = form.get("audio")
    tenant_id = form.get("tenant_id", "")
    phone = form.get("phone", "")
    mime_type = form.get("mime_type", "audio/ogg")

    if not audio_file:
        raise HTTPException(status_code=400, detail="Missing audio file")

    if not phone:
        raise HTTPException(status_code=400, detail="Missing phone in request")

    # Look up tenant
    resolved_tenant_id = registry.lookup_by_phone(phone)
    if tenant_id:
        if resolved_tenant_id != tenant_id:
            raise HTTPException(status_code=400, detail="Phone number does not match tenant_id")
    else:
        tenant_id = resolved_tenant_id

    if not tenant_id:
        raise HTTPException(status_code=404, detail="No tenant found for phone number")

    tenant_logger = TenantLogAdapter(logger, tenant_id)
    tenant_logger.info("Received WhatsApp audio message")

    # Save audio to temp file
    import tempfile
    import hashlib

    audio_bytes = await audio_file.read()
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()

    # Check cache first
    from agntrick.services.audio_transcription_cache import AudioTranscriptionCache
    cache = AudioTranscriptionCache()
    cached = cache.get(audio_hash, tenant_id)

    if cached:
        tenant_logger.info("Using cached transcription for audio hash %s", audio_hash[:8])
        transcribed_text = cached["transcription"]
    else:
        # Save to temp file for transcription
        ext_map = {"audio/ogg": ".ogg", "audio/opus": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a"}
        ext = ext_map.get(mime_type, ".ogg")
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            from agntrick.services.audio_transcriber import AudioTranscriber
            transcriber = AudioTranscriber()
            transcribed_text = await transcriber.transcribe_audio(tmp_path, mime_type)
            if transcribed_text.startswith("Error:"):
                tenant_logger.error("Transcription failed: %s", transcribed_text)
                raise HTTPException(status_code=500, detail=transcribed_text)
            # Cache the transcription
            cache.set(
                audio_hash=audio_hash,
                transcription=transcribed_text,
                mime_type=mime_type,
                tenant_id=tenant_id,
            )
            tenant_logger.info("Transcribed audio (%d bytes)", len(audio_bytes))
        finally:
            try:
                import os
                os.unlink(tmp_path)
            except Exception:
                pass

    # Run the agent with transcribed text
    message = f"[Voice message] {transcribed_text}"
    try:
        AgentRegistry.discover_agents()
        agent_cls = AgentRegistry.get(config.whatsapp.tenants[0].default_agent)
        # Find tenant config
        tenant_config = None
        for tenant in get_config().whatsapp.tenants:
            if tenant.id == tenant_id:
                tenant_config = tenant
                break
        if not tenant_config:
            raise HTTPException(status_code=404, detail="Tenant configuration not found")
        agent_cls = AgentRegistry.get(tenant_config.default_agent)
        if not agent_cls:
            raise HTTPException(status_code=500, detail="Agent not found")
        config = get_config()
        constructor_args = {
            "model_name": config.llm.model,
            "temperature": config.llm.temperature,
            "thread_id": "whatsapp_audio_webhook",
        }
        agent = agent_cls(**constructor_args)
        result = await agent.run(message)
        tenant_logger.info("Successfully processed audio message for tenant %s", tenant_id)
        return {"response": str(result) if result is not None else "", "tenant_id": tenant_id}
    except Exception as e:
        tenant_logger.error("Failed to process audio message for tenant %s: %s", tenant_id, str(e))
        raise HTTPException(status_code=500, detail="Internal error processing message")
```

- [ ] **Step 2: Write audio endpoint tests**

Create `tests/test_api/test_audio_route.py`:
```python
"""Tests for WhatsApp audio message endpoint."""
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agntrick.api.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)
class TestAudioRoute:
    @patch("agntrick.api.routes.whatsapp.get_whatsapp_registry")
    @patch("agntrick.api.routes.whatsapp.get_config")
    def test_audio_endpoint_missing_api_key(self, mock_config, mock_registry):
        mock_config.return_value = MagicMock(auth=MagicMock(api_keys={"test-key": "tenant1"}))
        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/channels/whatsapp/audio",
            files={"audio": ("test_audio_data", "audio/ogg")},
            data={"tenant_id": "t1", "phone": "1234567890", "mime_type": "8audio/ogg"},
        )
        assert response.status_code == 401

    @patch("agntrick.api.routes.whatsapp.get_config")
    def test_audio_endpoint_no_audio_file(self, mock_config):
        mock_config.return_value = MagicMock(auth=MagicMock(api_keys={"test-key": "tenant1"}))
        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/channels/whatsapp/audio",
            data={"tenant_id": "t1", "phone": "1234567890"},
        )
        assert response.status_code == 400
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/test_api/test_audio_route.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/agntrick/api/routes/whatsapp.py tests/test_api/test_audio_route.py
git commit -m "feat(api): add audio transcription endpoint with caching"
```
### Task 8: Update assistant prompt for audio awareness
**Files:**
- Modify: `src/agntrick/prompts/assistant.md:8-14`

- [ ] **Step 1: Add voice message awareness to prompt**

In `src/agntrick/prompts/assistant.md`, add after line 14 (in `<capabilities>` section):
```markdown
7. Process voice messages transcribed from WhatsApp audio — respond naturally when you see "[Voice message]" prefix
```

- [ ] **Step 2: Commit**

```bash
git add src/agntrick/prompts/assistant.md
git commit -m "docs: add voice message awareness to assistant prompt"
```
---

## Phase 5: Verification
### Task 9: Run full test suite and verify

- [ ] **Step 1: Run Go tests**

Run: `cd gateway && go test ./... -v`
Expected: All tests PASS

- [ ] **Step 2: Run Python tests**

Run: `cd /Users/jeancsil/code/agents && uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 3: Run linter**

Run: `cd /Users/jeancsil/code/agents && make check`
Expected: All checks PASS (mypy + ruff)

