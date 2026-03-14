#!/usr/bin/env bash
# Release script for agntrick package
#
# Usage:
#   ./scripts/release.sh 0.3.0
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - No uncommitted changes
#   - All tests passing
#
# Environment Variables:
#   - FORCE_RELEASE=1: Bypass branch check (use with caution)
#
# Note: agntrick-whatsapp is released from its own repository

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

validate_version() {
    if [[ ! $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        log_error "Invalid version format: $1 (expected X.Y.Z)"
    fi
}

check_branch() {
    local current_branch
    current_branch=$(git branch --show-current)

    if [[ "$current_branch" != "main" ]]; then
        if [[ "${FORCE_RELEASE}" != "1" ]]; then
            echo ""
            log_error "You are on branch '$current_branch', but releases should be done from 'main'."
            echo ""
            echo "To proceed anyway, set FORCE_RELEASE=1:"
            echo "  FORCE_RELEASE=1 ./scripts/release.sh $VERSION"
            echo ""
            echo "Or switch to main branch first:"
            echo "  git checkout main"
            echo "  git pull origin main"
            exit 1
        else
            log_warn "Bypassing branch check on '$current_branch' (FORCE_RELEASE=1)"
        fi
    fi
}

check_clean() {
    if [[ -n $(git status --porcelain) ]]; then
        log_error "Uncommitted changes detected. Commit or stash first."
    fi
}

check_gh() {
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is required but not installed."
    fi
}

update_version() {
    local file=$1
    local version=$2
    sed -i.bak "s/^version = \".*\"/version = \"$version\"/" "$file" && rm -f "${file}.bak"
    log_info "Updated $file to version $version"
}

run_tests() {
    log_info "Running tests..."
    make check && make test || log_error "Tests failed. Aborting release."
}

create_release() {
    local tag=$1
    local notes=$2

    log_info "Creating GitHub release $tag..."
    gh release create "$tag" --title "$tag" --notes "$notes" || log_error "Failed to create release"
}

# Main logic
VERSION=${1:-}

if [[ -z "$VERSION" ]]; then
    log_error "Usage: $0 VERSION"
fi

validate_version "$VERSION"

check_gh
check_clean
check_branch

update_version "pyproject.toml" "$VERSION"
run_tests
git add pyproject.toml
git commit -m "release: bump agntrick to $VERSION"
git tag -a "v$VERSION" -m "Release v$VERSION"
git push origin main --tags
create_release "v$VERSION" "## agntrick v$VERSION\n\nReleased via ./scripts/release.sh"
log_info "Released agntrick v$VERSION"
