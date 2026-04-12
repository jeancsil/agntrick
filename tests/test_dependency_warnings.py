"""Tests for dependency warning suppression on startup."""

import warnings

from agntrick.config import AgntrickConfig, LoggingConfig
from agntrick.logging_config import setup_logging


class TestDependencyWarningSuppression:
    """Tests that RequestsDependencyWarning is filtered at startup."""

    def test_urllib3_warning_filter_is_registered(self, tmp_path):
        """Setup logging registers a filter for urllib3 deprecation warnings."""
        # Save and restore logging state to avoid polluting other tests
        import logging

        root_logger = logging.getLogger()
        saved_handlers = list(root_logger.handlers)
        saved_level = root_logger.level

        try:
            config = AgntrickConfig(logging=LoggingConfig(level="INFO", directory=str(tmp_path)))
            setup_logging(config)

            filters = warnings.filters
            urllib3_filters = [f for f in filters if f[2] is not None and "urllib3" in str(f[2])]
            assert len(urllib3_filters) > 0, "No warning filter found for urllib3"
        finally:
            # Restore logging state
            root_logger.handlers.clear()
            for handler in saved_handlers:
                root_logger.addHandler(handler)
            root_logger.setLevel(saved_level)
