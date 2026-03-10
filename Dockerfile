# Use official Python image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv for Python package management
# Copy from the official installer: https://github.com/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Search Tools and Network Diagnostics
# ripgrep: ultra-fast text searching
# fd-find: user-friendly alternative to 'find'
# fzf: general-purpose command-line fuzzy finder
# libmagic: Required by neonize/python-magic for file type detection
# curl: For testing HTTP/HTTPS connections
# dnsutils: For DNS resolution troubleshooting
# ffmpeg: Required by pydub for audio conversion (WhatsApp voice messages are OGG format)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ripgrep \
    fd-find \
    fzf \
    libmagic1 \
    curl \
    dnsutils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Note: In Debian/Ubuntu, the 'fd' executable is renamed to 'fdfind'.
# We create a symbolic link so the agent can just call 'fd'.
RUN ln -s $(which fdfind) /usr/local/bin/fd

# Python Environment Setup

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy project files needed for dependency installation
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY config ./config

# Install dependencies using uv
# This installs the package in editable mode with all dependencies
RUN uv sync --frozen --no-dev

# The source code will be mounted as a volume at runtime
# This allows for live code changes without rebuilding the image
# The volume mount will override the src/ directory copied above

# Create logs directory
RUN mkdir -p /app/logs

# Set the default command to show help
CMD ["uv", "run", "agntrick", "--help"]
