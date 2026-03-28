package main

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// Config represents the main configuration structure from .agntrick.yaml
type Config struct {
	API      APIConfig      `yaml:"api"`
	WhatsApp WhatsAppConfig `yaml:"whatsapp"`
	Storage  StorageConfig  `yaml:"storage"`
}

// APIConfig holds API server configuration
type APIConfig struct {
	Host string `yaml:"host"`
	Port int    `yaml:"port"`
}

// WhatsAppConfig holds WhatsApp multi-tenant configuration
type WhatsAppConfig struct {
	Tenants []TenantConfig `yaml:"tenants"`
}

// TenantConfig represents a single WhatsApp tenant
type TenantConfig struct {
	ID              string   `yaml:"id"`
	Phone           string   `yaml:"phone"`
	DefaultAgent    string   `yaml:"default_agent"`
	AllowedContacts []string `yaml:"allowed_contacts"`
}

// StorageConfig holds storage configuration
type StorageConfig struct {
	BasePath string `yaml:"base_path"`
}

// LoadConfig reads and parses the .agntrick.yaml configuration file
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}

	// Apply defaults
	if config.API.Host == "" {
		config.API.Host = "127.0.0.1"
	}
	if config.API.Port == 0 {
		config.API.Port = 8000
	}
	if config.Storage.BasePath == "" {
		homeDir, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("failed to get home directory for default storage path: %w", err)
		}
		config.Storage.BasePath = fmt.Sprintf("%s/.local/share/agntrick", homeDir)
	}

	return &config, nil
}

// GetTenantByID finds a tenant by ID
func (c *Config) GetTenantByID(id string) (*TenantConfig, error) {
	for _, tenant := range c.WhatsApp.Tenants {
		if tenant.ID == id {
			return &tenant, nil
		}
	}
	return nil, fmt.Errorf("tenant with ID '%s' not found", id)
}

// Validate checks if the configuration is valid
func (c *Config) Validate() error {
	if len(c.WhatsApp.Tenants) == 0 {
		return fmt.Errorf("no tenants configured")
	}

	tenantIDs := make(map[string]bool)
	for _, tenant := range c.WhatsApp.Tenants {
		if tenant.ID == "" {
			return fmt.Errorf("tenant has empty ID")
		}
		if tenant.Phone == "" {
			return fmt.Errorf("tenant '%s' has empty phone", tenant.ID)
		}
		if tenant.DefaultAgent == "" {
			return fmt.Errorf("tenant '%s' has empty default_agent", tenant.ID)
		}

		if tenantIDs[tenant.ID] {
			return fmt.Errorf("duplicate tenant ID: '%s'", tenant.ID)
		}
		tenantIDs[tenant.ID] = true
	}

	return nil
}
