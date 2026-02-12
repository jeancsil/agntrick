# Use official Python image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv for Python package management
# Copy from the official installer: https://github.com/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy project files needed for dependency installation
COPY agentic-framework/pyproject.toml agentic-framework/uv.lock ./agentic-framework/
COPY agentic-framework/README.md ./agentic-framework/
COPY agentic-framework/src ./agentic-framework/src

# Install dependencies using uv
# This installs the package in editable mode with all dependencies
RUN uv sync --directory agentic-framework --frozen --no-dev

# The source code will be mounted as a volume at runtime
# This allows for live code changes without rebuilding the image
# The volume mount will override the src/ directory copied above

# Create logs directory
RUN mkdir -p /app/agentic-framework/logs

# Set the default command to show help
CMD ["uv", "--directory", "agentic-framework", "run", "agentic-run", "--help"]
