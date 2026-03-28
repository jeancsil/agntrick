package main

import (
	"context"
	"fmt"
	"strings"

	waE2E "go.mau.fi/whatsmeow/binary/proto"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"google.golang.org/protobuf/proto"
)

// handleMessage handles incoming WhatsApp messages.
// Self-messages are detected by checking IsFromMe + Chat==Sender (JID equality).
// This works for both phone-based JIDs (34677427318@s.whatsapp.net) and LID-based JIDs (118657162162293@lid).
func handleMessage(eh *EventHandler, msg *events.Message) {
	logger := eh.logger.With().Str("tenant_id", eh.tenantID).Logger()

	// Log all message details for diagnostics
	logger.Info().
		Str("chat", msg.Info.Chat.String()).
		Str("chat_user", msg.Info.Chat.User).
		Str("chat_server", msg.Info.Chat.Server).
		Str("sender", msg.Info.Sender.String()).
		Str("sender_user", msg.Info.Sender.User).
		Bool("is_from_me", msg.Info.IsFromMe).
		Msg("Received message event in handleMessage")

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

	logger.Info().Str("message", messageText).Msg("Extracted message text")

	// Use chat JID for sending responses (like the old code used chat_jid for self-messages)
	targetJID := msg.Info.Chat

	// Send typing indicator
	_ = eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresenceComposing, types.ChatPresenceMediaText)

	// Forward to Python API
	response, err := forwardToPythonAPI(eh, messageText)
	if err != nil {
		logger.Error().Err(err).Msg("Failed to forward message to Python API")
		_ = eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText)
		return
	}

	// Send response back to WhatsApp
	if err := sendResponseToWhatsApp(eh, response, targetJID); err != nil {
		logger.Error().Err(err).Msg("Failed to send response back to WhatsApp")
	}

	// Clear typing indicator
	_ = eh.session.SendChatPresence(context.Background(), targetJID, types.ChatPresencePaused, types.ChatPresenceMediaText)
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

// forwardToPythonAPI forwards the message to the Python API
func forwardToPythonAPI(eh *EventHandler, messageText string) (string, error) {
	tenant, err := eh.manager.config.GetTenantByID(eh.tenantID)
	if err != nil {
		return "", fmt.Errorf("failed to get tenant config: %w", err)
	}

	return eh.manager.httpClient.ForwardMessage(eh.tenantID, tenant.Phone, messageText)
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
