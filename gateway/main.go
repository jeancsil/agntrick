package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/rs/zerolog"
)

const (
	defaultConfigPath = ".agntrick.yaml"
)

func main() {
	// Setup structured logging
	logger := setupLogger()

	// Get config path from environment or use default
	configPath := os.Getenv("AGNTRICK_CONFIG")
	if configPath == "" {
		configPath = defaultConfigPath
	}

	logger.Info().Str("config", configPath).Msg("Loading configuration")

	// Load configuration
	config, err := LoadConfig(configPath)
	if err != nil {
		logger.Fatal().Err(err).Msg("Failed to load configuration")
	}

	// Validate configuration
	if err := config.Validate(); err != nil {
		logger.Fatal().Err(err).Msg("Invalid configuration")
	}

	logger.Info().
		Str("api_host", config.API.Host).
		Int("api_port", config.API.Port).
		Str("storage_base_path", config.Storage.BasePath).
		Msg("Configuration loaded successfully")

	// Print loaded tenants
	logger.Info().Int("count", len(config.WhatsApp.Tenants)).Msg("Loaded WhatsApp tenants")
	for _, tenant := range config.WhatsApp.Tenants {
		logger.Info().
			Str("id", tenant.ID).
			Str("phone", tenant.Phone).
			Str("default_agent", tenant.DefaultAgent).
			Int("allowed_contacts", len(tenant.AllowedContacts)).
			Msg("Tenant")
	}

	// TODO: Initialize session manager for multi-tenant WhatsApp sessions
	// TODO: Start HTTP server for receiving messages from Python API
	// TODO: Setup signal handlers for graceful shutdown

	// Setup graceful shutdown
	setupGracefulShutdown(logger)
}

func setupLogger() zerolog.Logger {
	// Use console writer for human-readable output
	logger := zerolog.New(os.Stdout).With().Timestamp().Logger()

	// Set log level from environment
	logLevel := os.Getenv("LOG_LEVEL")
	if logLevel == "" {
		logLevel = "info"
	}

	level, err := zerolog.ParseLevel(logLevel)
	if err != nil {
		log.Printf("Invalid log level '%s', using 'info': %v", logLevel, err)
		level = zerolog.InfoLevel
	}

	logger = logger.Level(level)

	return logger
}

func setupGracefulShutdown(logger zerolog.Logger) {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	sig := <-sigChan
	logger.Info().Str("signal", sig.String()).Msg("Received shutdown signal")

	// TODO: Close all WhatsApp sessions gracefully
	// TODO: Flush any pending messages

	logger.Info().Msg("Gateway shutdown complete")
	os.Exit(0)
}

func getAPIURL(config *Config) string {
	return fmt.Sprintf("http://%s:%d", config.API.Host, config.API.Port)
}
