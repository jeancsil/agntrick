package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/rs/zerolog"
	waE2E "go.mau.fi/whatsmeow/binary/proto"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"google.golang.org/protobuf/proto"
)

// handleMessage handles incoming WhatsApp messages.
// Self-messages are detected by checking IsFromMe + Chat==Sender (JID equality).
// This works for both phone-based JIDs (34677427318@s.whatsapp.net) and LID-based JIDs (118657162162293@lid).
func handleMessage(eh *EventHandler, msg *events.Message) {
	startTime := time.Now()
	logger := eh.logger.With().Str("tenant_id", eh.tenantID).Logger()

	logger.Info().
		Str("chat", msg.Info.Chat.String()).
		Str("sender", msg.Info.Sender.String()).
		Bool("is_from_me", msg.Info.IsFromMe).
		Msg("Processing incoming message")

	// Reject group messages
	if msg.Info.Chat.Server == types.GroupServer {
		logger.Debug().Msg("Ignoring group message")
		return
	}

	// Check if this is a self-message (from the authenticated user to themselves)
	if !isSelfMessage(eh, msg) {
		logger.Info().
			Str("chat", msg.Info.Chat.String()).
			Str("sender", msg.Info.Sender.String()).
			Bool("is_from_me", msg.Info.IsFromMe).
			Msg("Ignoring non-self message")
		return
	}

	logger.Info().Msg("Processing self-message")

	// Extract message text
	messageText := extractMessageText(msg)
	if messageText == "" {
		logger.Warn().Msg("Message has no text content to process")
		return
	}

	// Use chat JID for sending responses (like the old code used chat_jid for self-messages)
	targetJID := msg.Info.Chat

	// Start persistent typing indicator that re-sends composing presence every 3 seconds.
	// WhatsApp auto-expires typing indicators after ~3-5 seconds, so we must refresh
	// to keep the indicator visible during long LLM processing (90+ seconds).
	typingCtx, cancelTyping := context.WithCancel(context.Background())
	defer cancelTyping()

	go func() {
		logger.Debug().Msg("Typing indicator loop started")
		ticker := time.NewTicker(3 * time.Second)
		defer ticker.Stop()

		// Send initial composing presence immediately
		_ = eh.session.SendChatPresence(typingCtx, targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText)

		for {
			select {
			case <-ticker.C:
				_ = eh.session.SendChatPresence(typingCtx, targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText)
			case <-typingCtx.Done():
				logger.Debug().Msg("Typing indicator loop stopped")
				return
			}
		}
	}()

	// Forward to Python API with progress logging
	response, err := forwardToPythonAPI(eh, messageText, logger)

	// Stop typing indicator loop
	cancelTyping()

	elapsed := time.Since(startTime)

	if err != nil {
		logger.Error().Err(err).
			Dur("elapsed", elapsed).
			Msg("Failed to forward message to Python API")
		_ = eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText)
		return
	}

	// Send response back to WhatsApp
	if err := sendResponseToWhatsApp(eh, response, targetJID); err != nil {
		logger.Error().Err(err).Msg("Failed to send response back to WhatsApp")
	}

	// Clear typing indicator
	_ = eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText)

	logger.Info().
		Dur("elapsed", time.Since(startTime)).
		Int("response_len", len(response)).
		Msg("Message processing completed")
}

// isSelfMessage checks if the message is from the user to themselves.
// Detection strategy (in order):
//  1. Chat == Sender (exact JID match) — works when both use same format
//  2. Chat matches Store.ID (phone-based) — handles mixed format cases
//  3. Chat matches Store.LID (LID-based) — handles LID-only Chat JIDs
//  4. Phone number fallback against tenant config — last resort
func isSelfMessage(eh *EventHandler, msg *events.Message) bool {
	if !msg.Info.IsFromMe {
		return false
	}

	chat := msg.Info.Chat

	// Case 1: Chat and Sender are the same JID (exact match)
	if chat.User == msg.Info.Sender.User && chat.Server == msg.Info.Sender.Server {
		return true
	}

	// Case 2: Chat matches the authenticated device's phone-based JID
	if eh.session.Store.ID != nil {
		ownJID := eh.session.Store.ID.ToNonAD()
		if chat.User == ownJID.User && chat.Server == ownJID.Server {
			return true
		}
	}

	// Case 3: Chat matches the authenticated device's LID
	// WhatsApp may route "note to self" messages using LID-based Chat JIDs
	// while Sender uses phone-based JID — Store.LID bridges the gap.
	if storeLID := eh.session.Store.LID; storeLID.User != "" {
		if chat.User == storeLID.User && chat.Server == storeLID.Server {
			return true
		}
	}

	// Case 4: Phone number fallback against tenant config
	tenant, err := eh.manager.config.GetTenantByID(eh.tenantID)
	if err != nil {
		eh.logger.Error().Err(err).Msg("Failed to get tenant config for self-message check")
		return false
	}

	normalizedTenantPhone := normalizePhoneNumber(tenant.Phone)
	normalizedChat := normalizePhoneNumber(chat.String())

	if normalizedChat == normalizedTenantPhone {
		return true
	}

	eh.logger.Info().
		Str("tenant_phone", normalizedTenantPhone).
		Str("chat", chat.String()).
		Str("sender", msg.Info.Sender.String()).
		Msg("Self-message phone number mismatch")
	return false
}

// normalizePhoneNumber normalizes a phone number or JID to digits only.
// Strips JID domain (@s.whatsapp.net, @lid, etc.), device suffixes, and non-digit characters.
func normalizePhoneNumber(jidOrPhone string) string {
	// Remove JID domain if present (e.g., "34677427318@s.whatsapp.net" -> "34677427318")
	if idx := strings.Index(jidOrPhone, "@"); idx > 0 {
		jidOrPhone = jidOrPhone[:idx]
	}
	// Remove device suffix if present (e.g., "34677427318.0:21" -> "34677427318")
	if idx := strings.Index(jidOrPhone, "."); idx > 0 {
		jidOrPhone = jidOrPhone[:idx]
	}
	// Keep only digits
	var digits strings.Builder
	for _, ch := range jidOrPhone {
		if ch >= '0' && ch <= '9' {
			digits.WriteRune(ch)
		}
	}
	return digits.String()
}

// isSelfMessageForTesting provides a testable version of isSelfMessage logic.
// Checks if a message from the user (isFromMe) is in their own chat.
// Uses phone-based JID comparison via normalization.
func isSelfMessageForTesting(isFromMe bool, chat string, storeID string) bool {
	if !isFromMe {
		return false
	}
	return normalizePhoneNumber(chat) == normalizePhoneNumber(storeID)
}

// extractMessageText extracts the text content from a message.
// Checks both Conversation (simple text) and ExtendedTextMessage.Text
// (WhatsApp often wraps "note to self" messages in ExtendedTextMessage).
func extractMessageText(msg *events.Message) string {
	if msg.Message == nil {
		return ""
	}

	// Check Conversation field (simple text messages)
	if conversation := msg.Message.GetConversation(); conversation != "" {
		return conversation
	}

	// Check ExtendedTextMessage.Text (messages with link previews, forwarded, etc.)
	if etm := msg.Message.GetExtendedTextMessage(); etm != nil {
		if text := etm.GetText(); text != "" {
			return text
		}
	}

	return ""
}

// forwardToPythonAPI forwards the message to the Python API and logs progress during the LLM wait.
// Spawns a background goroutine that logs status every 15 seconds until the API responds.
func forwardToPythonAPI(eh *EventHandler, messageText string, logger zerolog.Logger) (string, error) {
	tenant, err := eh.manager.config.GetTenantByID(eh.tenantID)
	if err != nil {
		return "", fmt.Errorf("failed to get tenant config: %w", err)
	}

	// Start progress logger for the LLM call
	progressCtx, cancelProgress := context.WithCancel(context.Background())
	defer cancelProgress()

	startTime := time.Now()
	go logLLMProgress(progressCtx, logger, startTime)

	logger.Info().Msg("Forwarding message to Python API (waiting for LLM response)")

	response, err := eh.manager.httpClient.ForwardMessage(eh.tenantID, tenant.Phone, messageText)

	cancelProgress()

	if err != nil {
		return "", err
	}

	logger.Info().
		Dur("elapsed", time.Since(startTime)).
		Msg("LLM response received")

	return response, nil
}

// logLLMProgress logs periodic INFO-level status updates while waiting for an LLM response.
// Stops when the context is cancelled (i.e., when the API responds or errors).
const llmProgressInterval = 15 * time.Second

func logLLMProgress(ctx context.Context, logger zerolog.Logger, startTime time.Time) {
	ticker := time.NewTicker(llmProgressInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			elapsed := time.Since(startTime)
			logger.Info().
				Dur("elapsed", elapsed).
				Msg("Still waiting for LLM response")
		case <-ctx.Done():
			return
		}
	}
}

// sendResponseToWhatsApp sends the API response back to WhatsApp
// targetJID should be msg.Info.Chat for self-messages (matching old code's chat_jid approach)
func sendResponseToWhatsApp(eh *EventHandler, response string, targetJID types.JID) error {
	if response == "" {
		return fmt.Errorf("empty response from API")
	}

	eh.logger.Info().
		Str("target", targetJID.String()).
		Str("response_len", fmt.Sprintf("%d", len(response))).
		Msg("Sending response to WhatsApp")

	_, err := eh.session.SendMessage(context.Background(), targetJID, &waE2E.Message{
		Conversation: proto.String(response),
	})
	if err != nil {
		return fmt.Errorf("failed to send message: %w", err)
	}

	return nil
}
