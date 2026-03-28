package main

import (
	"fmt"

	"go.mau.fi/whatsmeow/types/events"
)

// handleMessage handles incoming WhatsApp messages
// Self-messages are detected via v.Info.IsFromMe && v.Info.Chat == client.Store.ID
func handleMessage(eh *EventHandler, msg *events.Message) {
	logger := eh.logger.With().Str("tenant_id", eh.tenantID).Logger()

	// Check if this is a self-message
	if !isSelfMessage(eh, msg) {
		logger.Debug().Msg("Ignoring non-self message")
		return
	}

	logger.Debug().Msg("Processing self-message")

	// Extract message text
	messageText := extractMessageText(msg)
	if messageText == "" {
		logger.Warn().Msg("Message has no text content to process")
		return
	}

	logger.Debug().Str("message", messageText).Msg("Extracted message text")

	// Forward to Python API
	response, err := forwardToPythonAPI(eh, messageText)
	if err != nil {
		logger.Error().Err(err).Msg("Failed to forward message to Python API")
		return
	}

	// Send response back to WhatsApp
	if err := sendResponseToWhatsApp(eh, response); err != nil {
		logger.Error().Err(err).Msg("Failed to send response back to WhatsApp")
	}
}

// isSelfMessage checks if the message is from the user themselves
// Self-messages are detected via v.Info.IsFromMe && v.Info.Chat == client.Store.ID
func isSelfMessage(eh *EventHandler, msg *events.Message) bool {
	// Check if message is from me
	if !msg.Info.IsFromMe {
		return false
	}

	// Check if message is in the user's own chat
	// Note: In the actual whatsmeow library, this comparison would use Equals method
	// For now, we'll use a string comparison to avoid type issues
	return msg.Info.Chat.String() == eh.session.Store.ID.String()
}

// isSelfMessageForTesting provides a testable version of isSelfMessage logic
func isSelfMessageForTesting(isFromMe bool, chat string, storeID string) bool {
	// Check if message is from me
	if !isFromMe {
		return false
	}

	// Check if message is in the user's own chat
	return chat == storeID
}

// extractMessageText extracts the text content from a message
func extractMessageText(msg *events.Message) string {
	// For text messages, get conversation content
	if msg.Message != nil {
		if conversation := msg.Message.GetConversation(); conversation != "" {
			return conversation
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
func sendResponseToWhatsApp(eh *EventHandler, response string) error {
	if response == "" {
		return fmt.Errorf("empty response from API")
	}

	// Get tenant config (though we don't use it for sending in this simple case)
	_, err := eh.manager.config.GetTenantByID(eh.tenantID)
	if err != nil {
		return fmt.Errorf("failed to get tenant config: %w", err)
	}

	// Send the response as a message to the user's own chat
	targetJID := eh.session.Store.ID.ToNonAD()

	// For now, we'll log the response since implementing proper WhatsApp protocol messaging
	// requires more complex message construction
	eh.logger.Info().Str("response", response).Str("to", targetJID.String()).Msg("Would send response back to WhatsApp")

	// TODO: Implement proper WhatsApp protocol message sending
	// This would involve constructing proper protocol messages using the whatsmeow library
	// and using eh.session.SendMessage with the correct message format

	return nil
}


