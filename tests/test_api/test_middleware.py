"""Tests for API middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agntrick.api.middleware import catch_exceptions_middleware, request_logging_middleware


class TestCatchExceptionsMiddleware:
    """Test catch exceptions middleware."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with exception middleware."""
        app = FastAPI()

        @app.get("/ok")
        def ok_handler():
            return {"status": "ok"}

        @app.get("/error")
        def error_handler():
            raise ValueError("Test error")

        # Register middleware (in reverse order for test)
        app.middleware("http")(catch_exceptions_middleware)
        return app

    def test_successful_request(self, app: FastAPI):
        """Test successful requests pass through normally."""
        client = TestClient(app)
        response = client.get("/ok")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_exception_handling_returns_500(self, app: FastAPI):
        """Test unhandled exceptions return sanitized 500 error."""
        client = TestClient(app)
        response = client.get("/error")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}


class TestRequestLoggingMiddleware:
    """Test request logging middleware."""

    @pytest.fixture
    def mock_logger(self, monkeypatch):
        """Mock logger for testing."""
        from unittest.mock import Mock

        logger = Mock()
        monkeypatch.setattr("agntrick.api.middleware.logger", logger)
        return logger

    @pytest.fixture
    def app(self, mock_logger) -> FastAPI:
        """Create test app with logging middleware."""
        app = FastAPI()

        @app.get("/test")
        async def test_handler():
            return {"message": "test"}

        # Register middleware
        app.middleware("http")(request_logging_middleware)
        return app

    def test_request_logging_includes_tenant_id_and_duration(self, app: FastAPI, mock_logger):
        """Test that request logging includes tenant_id and duration."""
        client = TestClient(app)

        # Test with API key
        response = client.get("/test", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200

        # Verify logger was called with expected args
        mock_logger.info.assert_called_once()
        all_args = mock_logger.info.call_args[0]

        # Check format: METHOD PATH TENANT_ID STATUS DURATION
        assert "GET" in all_args
        assert "/test" in all_args
        assert "test-key" in all_args

    def test_request_logging_without_api_key(self, app: FastAPI, mock_logger):
        """Test that request logging works without API key."""
        client = TestClient(app)

        # Test without API key
        response = client.get("/test")
        assert response.status_code == 200

        # Verify logger was called with anonymous tenant
        mock_logger.info.assert_called_once()
        all_args = mock_logger.info.call_args[0]
        assert "anonymous" in all_args


class TestRetryConfig:
    """Test retry configuration."""

    def test_default_config(self):
        """Test default retry configuration."""
        from agntrick.api.resilience import RetryConfig

        config = RetryConfig()
        assert config.max_retries == 3
        assert config.backoff_factor == 0.5

    def test_custom_config(self):
        """Test custom retry configuration."""
        from agntrick.api.resilience import RetryConfig

        config = RetryConfig(max_retries=5, backoff_factor=1.0)
        assert config.max_retries == 5
        assert config.backoff_factor == 1.0


class TestRetryAsync:
    """Test retry_async function."""

    @pytest.mark.asyncio
    async def test_retry_successful_first_attempt(self):
        """Test successful call on first attempt."""
        from agntrick.api.resilience import RetryConfig, retry_async

        async def success_func():
            return "success"

        result = await retry_async(success_func, RetryConfig(max_retries=2))
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_successful_after_failure(self):
        """Test successful call after initial failures."""
        from agntrick.api.resilience import RetryConfig, retry_async

        attempt_count = 0

        async def flaky_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        result = await retry_async(flaky_func, RetryConfig(max_retries=5))
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_fails_all_attempts(self):
        """Test that all retries fail and exception is raised."""
        from agntrick.api.resilience import RetryConfig, retry_async

        async def always_fail_func():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            await retry_async(always_fail_func, RetryConfig(max_retries=2))

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        """Test that retry uses exponential backoff."""
        import time

        from agntrick.api.resilience import RetryConfig, retry_async

        start_time = time.time()
        attempt_count = 0

        async def flaky_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        result = await retry_async(flaky_func, RetryConfig(max_retries=3, backoff_factor=0.1))
        end_time = time.time()

        assert result == "success"
        # Should have made 3 attempts with some delay
        assert attempt_count == 3
        # Should have taken more than 0.1s due to backoff
        assert end_time - start_time > 0.1
