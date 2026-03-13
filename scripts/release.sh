#!/usr/bin/env bash
# Release script for agntrick and agntrick-whatsapp packages
#
# Usage:
#   ./scripts/release.sh agntrick 0.3.0
#   ./scripts/release.sh agntrick-whatsapp 0.4.0
#   ./scripts/release.sh both 0.3.0 0.4.0
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - No uncommitted changes
#   - All tests passing
#
# Environment Variables:
#   - FORCE_RELEASE=1: Bypass branch check (use with caution)

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
            echo "  FORCE_RELEASE=1 make release VERSION=$2"
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

update_whatsapp_dependency() {
    local version=$1
    local file="packages/agntrick-whatsapp/pyproject.toml"
    sed -i.bak "s/agntrick>=[0-9]\+\.[0-9]\+\.[0-9]\+/agntrick>=$version/" "$file" && rm -f "${file}.bak"
    log_info "Updated agntrick dependency to >=$version in WhatsApp package"
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
PACKAGE=${1:-}
VERSION=${2:-}
WHATSAPP_VERSION=${3:-}

check_gh
check_clean
check_branch "$PACKAGE" "$VERSION"

case "$PACKAGE" in
    agntrick)
        validate_version "$VERSION"
        update_version "pyproject.toml" "$VERSION"
        run_tests
        git add pyproject.toml
        git commit -m "release: bump agntrick to $VERSION"
        git tag -a "v$VERSION" -m "Release v$VERSION"
        git push origin main --tags
        create_release "v$VERSION" "## agntrick v$VERSION\n\nReleased via make release"
        log_info "Released agntrick v$VERSION"
        ;;
    agntrick-whatsapp)
        validate_version "$VERSION"
        update_version "packages/agntrick-whatsapp/pyproject.toml" "$VERSION"
        run_tests
        git add packages/agntrick-whatsapp/pyproject.toml
        git commit -m "release: bump agntrick-whatsapp to $VERSION"
        git tag -a "agntrick-whatsapp-v$VERSION" -m "Release agntrick-whatsapp v$VERSION"
        git push origin main --tags
        create_release "agntrick-whatsapp-v$VERSION" "## agntrick-whatsapp v$VERSION\n\nReleased via make release-whatsapp"
        log_info "Released agntrick-whatsapp v$VERSION"
        ;;
    both)
        validate_version "$VERSION"
        validate_version "$WHATSAPP_VERSION"
        update_version "pyproject.toml" "$VERSION"
        update_version "packages/agntrick-whatsapp/pyproject.toml" "$WHATSAPP_VERSION"
        update_whatsapp_dependency "$VERSION"
        run_tests
        git add pyproject.toml packages/agntrick-whatsapp/pyproject.toml
        git commit -m "release: bump agntrick to $VERSION, agntrick-whatsapp to $WHATSAPP_VERSION"
        git tag -a "v$VERSION" -m "Release v$VERSION"
        git tag -a "agntrick-whatsapp-v$WHATSAPP_VERSION" -m "Release agntrick-whatsapp v$WHATSAPP_VERSION"
        git push origin main --tags
        create_release "v$VERSION" "## agntrick v$VERSION\n## agntrick-whatsapp v$WHATSAPP_VERSION"
        create_release "agntrick-whatsapp-v$WHATSAPP_VERSION" "## agntrick-whatsapp v$WHATSAPP_VERSION\n\nDepends on agntrick>=$VERSION"
        log_info "Released both packages"
        ;;
    *)
        log_error "Usage: $0 {agntrick|agntrick-whatsapp|both} VERSION [WHATSAPP_VERSION]"
        ;;
esac
