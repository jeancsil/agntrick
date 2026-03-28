package main

import (
	"encoding/json"
	"testing"
)

// Test_MessagePayload_JSON tests that the MessagePayload can be marshaled to JSON
func Test_MessagePayload_JSON(t *testing.T) {
	payload := MessagePayload{
		From:     "1234567890",
		Message:  "Hello, how are you?",
		TenantID: "test-tenant",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		t.Errorf("Failed to marshal MessagePayload: %v", err)
	}

	expected := `{"from":"1234567890","message":"Hello, how are you?","tenant_id":"test-tenant"}`
	if string(jsonData) != expected {
		t.Errorf("Expected JSON '%s', got '%s'", expected, string(jsonData))
	}
}

// Test_MessagePayload_JSON_WithSpecialCharacters tests JSON marshaling with special characters
func Test_MessagePayload_JSON_WithSpecialCharacters(t *testing.T) {
	payload := MessagePayload{
		From:     "+1234567890",
		Message:  "Hello! How are you? 😊",
		TenantID: "test-tenant-123",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		t.Errorf("Failed to marshal MessagePayload with special characters: %v", err)
	}

	expected := `{"from":"+1234567890","message":"Hello! How are you? 😊","tenant_id":"test-tenant-123"}`
	if string(jsonData) != expected {
		t.Errorf("Expected JSON '%s', got '%s'", expected, string(jsonData))
	}
}

// Test_MessagePayload_JSON_EmptyFields tests JSON marshaling with empty fields
func Test_MessagePayload_JSON_EmptyFields(t *testing.T) {
	payload := MessagePayload{
		From:     "",
		Message:  "",
		TenantID: "",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		t.Errorf("Failed to marshal MessagePayload with empty fields: %v", err)
	}

	expected := `{"from":"","message":"","tenant_id":""}`
	if string(jsonData) != expected {
		t.Errorf("Expected JSON '%s', got '%s'", expected, string(jsonData))
	}
}

// Test_isSelfMessageForTesting_selfMessage tests that isSelfMessageForTesting returns true for self-messages
func Test_isSelfMessageForTesting_selfMessage(t *testing.T) {
	result := isSelfMessageForTesting(true, "1234567890@s.whatsapp.net", "1234567890@s.whatsapp.net")
	if !result {
		t.Errorf("Expected isSelfMessageForTesting to return true for self-messages, got false")
	}
}

// Test_isSelfMessageForTesting_nonSelfMessage tests that isSelfMessageForTesting returns false for non-self messages
func Test_isSelfMessageForTesting_nonSelfMessage(t *testing.T) {
	result := isSelfMessageForTesting(false, "other@s.whatsapp.net", "1234567890@s.whatsapp.net")
	if result {
		t.Errorf("Expected isSelfMessageForTesting to return false for non-self messages, got true")
	}
}

// Test_isSelfMessageForTesting_differentChat tests that isSelfMessageForTesting returns false for messages from different chats
func Test_isSelfMessageForTesting_differentChat(t *testing.T) {
	result := isSelfMessageForTesting(true, "different-group@s.whatsapp.net", "1234567890@s.whatsapp.net")
	if result {
		t.Errorf("Expected isSelfMessageForTesting to return false for messages from different chats, got true")
	}
}


// MockMessage simulates a simplified Message struct for testing
type MockMessage struct {
	Conversation *string
}

func (m MockMessage) GetConversation() string {
	if m.Conversation != nil {
		return *m.Conversation
	}
	return ""
}