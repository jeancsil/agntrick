# PyPI Release 1.0.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `agntrick` package publishable to PyPI and automate releases with semver pre-release support (e.g. `1.0.0-alpha`, `1.0.0-beta.1`, `1.0.0-rc.2`).

**Architecture:** Single Python package `agntrick` published to PyPI. The Go gateway stays as a compiled binary deployed via Docker -- it is NOT a separate PyPI package. The release script (`scripts/release.sh`) will be the single entry point for all releases, updating version numbers, running checks, tagging, and pushing. GitHub Actions will auto-publish to PyPI on release tags, with pre-release tags going to TestPyPI first.

**Tech Stack:** Python 3.12+, setuptools, uv, GitHub Actions (Trusted Publishers OIDC), gh CLI

---

## File Structure

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/agntrick/__init__.py` | Fix `__version__` to be auto-synced from pyproject.toml |
| Modify | `pyproject.toml` | Version bump to `1.0.0-alpha`, ensure package-data is correct |
| Rewrite | `scripts/release.sh` | Support pre-release semver, single-package, update `__init__.py` too |
| Rewrite | `.github/workflows/release.yml` | Remove dead WhatsApp jobs, add pre-release detection |
| Modify | `Makefile` | Remove WhatsApp release targets, simplify |
| Delete | (nothing) | All files modified in-place |

---

### Task 1: Sync `__version__` from pyproject.toml automatically

**Files:**
- Modify: `src/agntrick/__init__.py:79`
- Modify: `pyproject.toml:3`

**Why:** Currently `pyproject.toml` says `0.4.3` but `__init__.py` says `0.2.8`. The simplest fix is to read the version from pyproject.toml at import time using `importlib.metadata`, which is the standard Python pattern. No need to keep two version numbers in sync manually.

- [ ] **Step 1: Update `__init__.py` to read version from package metadata**

Replace line 79 of `src/agntrick/__init__.py`:

```python
__version__ = "0.2.8"
```

with:

```python
try:
    from importlib.metadata import version as _get_version

    __version__ = _get_version("agntrick")
except Exception:
    __version__ = "0.0.0"
```

This reads the version that setuptools installed from `pyproject.toml`. The fallback handles editable installs during development.

- [ ] **Step 2: Update `pyproject.toml` version to `1.0.0-alpha`**

Replace line 3 of `pyproject.toml`:

```toml
version = "0.4.3"
```

with:

```toml
version = "1.0.0-alpha"
```

- [ ] **Step 3: Verify the version is readable**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && uv sync && uv run python -c "import agntrick; print(agntrick.__version__)"
```

Expected: `1.0.0-alpha` (may show `0.4.3` on first try if uv sync hasn't picked up the change -- if so, run `uv pip install -e .` then retry).

- [ ] **Step 4: Run checks**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && make check
```

Expected: PASS (no errors)

- [ ] **Step 5: Run tests**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && make test
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agntrick/__init__.py pyproject.toml
git commit -m "feat: sync version from pyproject.toml via importlib.metadata, bump to 1.0.0-alpha"
```

---

### Task 2: Rewrite `scripts/release.sh` for single-package semver releases

**Files:**
- Rewrite: `scripts/release.sh`

**Why:** The current script only accepts `X.Y.Z` format and references the old multi-package workflow. The new script must:
1. Accept full semver including pre-release: `1.0.0-alpha`, `1.0.0-beta.1`, `1.0.0-rc.2`, `1.0.0`
2. Update only `pyproject.toml` (version is auto-synced via importlib.metadata)
3. Detect pre-release and mark the GitHub release accordingly (so CI sends pre-releases to TestPyPI)
4. Be a single-package script (no `agntrick-whatsapp` logic)

- [ ] **Step 1: Rewrite `scripts/release.sh`**

Replace the entire contents of `scripts/release.sh` with:

```bash
#!/usr/bin/env bash
# Release script for agntrick
#
# Usage:
#   ./scripts/release.sh 1.0.0-alpha
#   ./scripts/release.sh 1.0.0-beta.1
#   ./scripts/release.sh 1.0.0-rc.2
#   ./scripts/release.sh 1.0.0
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - No uncommitted changes
#   - All tests passing
#
# Pre-release versions (containing -alpha, -beta, -rc) are published to
# TestPyPI. Stable versions are published to PyPI.
#
# Environment Variables:
#   - FORCE_RELEASE=1: Bypass branch check (use with caution)
#   - SKIP_TESTS=1:    Skip test execution

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Validation ──────────────────────────────────────────────────────

validate_version() {
    local version="$1"
    # Full semver: X.Y.Z with optional pre-release (-alpha, -beta.1, -rc.2, etc.)
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*)?$ ]]; then
        log_error "Invalid version: '$version' (expected X.Y.Z or X.Y.Z-prerelease)"
    fi
}

is_prerelease() {
    [[ "$1" == *"-"* ]]
}

check_branch() {
    local current_branch
    current_branch=$(git branch --show-current)
    if [[ "$current_branch" != "main" ]]; then
        if [[ "${FORCE_RELEASE:-}" != "1" ]]; then
            echo ""
            log_error "Releases must be from 'main' (currently: '$current_branch').
  Use FORCE_RELEASE=1 to bypass, or:
    git checkout main && git pull origin main"
        else
            log_warn "Bypassing branch check on '$current_branch'"
        fi
    fi
}

check_clean() {
    if [[ -n $(git status --porcelain) ]]; then
        log_error "Uncommitted changes. Commit or stash first."
    fi
}

check_gh() {
    if ! command -v gh &>/dev/null; then
        log_error "GitHub CLI (gh) is required. Install: https://cli.github.com"
    fi
}

# ── Actions ─────────────────────────────────────────────────────────

update_version() {
    local version="$1"
    sed -i.bak "s/^version = \".*\"/version = \"$version\"/" pyproject.toml
    rm -f pyproject.toml.bak
    log_info "Updated pyproject.toml to $version"
}

run_checks() {
    log_info "Running make check..."
    make check
}

run_tests() {
    if [[ "${SKIP_TESTS:-}" == "1" ]]; then
        log_warn "Skipping tests (SKIP_TESTS=1)"
        return
    fi
    log_info "Running make test..."
    make test
}

create_tag_and_release() {
    local version="$1"
    local tag="v$version"
    local prerelease=""

    if is_prerelease "$version"; then
        prerelease="--prerelease"
        log_info "Detected pre-release: $version"
    fi

    log_info "Creating tag $tag..."
    git tag -a "$tag" -m "Release $tag"

    log_info "Pushing to origin..."
    git push origin HEAD --tags

    log_info "Creating GitHub release $tag..."
    local notes="## agntrick $tag

Released $(date +%Y-%m-%d)."

    gh release create "$tag" --title "$tag" --notes "$notes" $prerelease

    if is_prerelease "$version"; then
        log_info "Pre-release published. GitHub Actions will publish to TestPyPI."
    else
        log_info "Stable release published. GitHub Actions will publish to PyPI."
    fi
}

# ── Main ────────────────────────────────────────────────────────────

main() {
    local version="${1:-}"

    if [[ -z "$version" ]]; then
        log_error "Usage: $0 VERSION
  Examples:
    $0 1.0.0-alpha
    $0 1.0.0-beta.1
    $0 1.0.0-rc.2
    $0 1.0.0"
    fi

    validate_version "$version"
    check_gh
    check_clean
    check_branch

    update_version "$version"
    run_checks
    run_tests

    git add pyproject.toml
    git commit -m "release: agntrick $version"

    create_tag_and_release "$version"

    echo ""
    log_info "Done! agntrick $version released."
    echo "  Tag: v$version"
    if is_prerelease "$version"; then
        echo "  PyPI: https://test.pypi.org/p/agntrick (pre-release)"
    else
        echo "  PyPI: https://pypi.org/p/agntrick"
    fi
    echo "  GitHub: https://github.com/jeancsil/agntrick/releases/tag/v$version"
}

main "$@"
```

- [ ] **Step 2: Ensure the script is executable**

Run:
```bash
chmod +x scripts/release.sh
```

- [ ] **Step 3: Test the version validation logic**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api
# These should print validation error (version is missing) but prove script runs:
bash scripts/release.sh 2>&1 | head -5
```

Expected: Usage message printed (no segfault or syntax error).

- [ ] **Step 4: Commit**

```bash
git add scripts/release.sh
git commit -m "feat: rewrite release.sh for semver pre-release support"
```

---

### Task 3: Simplify `Makefile` release targets

**Files:**
- Modify: `Makefile:92-105`

**Why:** Remove `release-whatsapp` and `release-both` targets since there is no separate `agntrick-whatsapp` package. Keep only the single `release` target.

- [ ] **Step 1: Remove WhatsApp release targets from Makefile**

Replace lines 92-105 of `Makefile` (the `## -- Release Commands --` section) with:

```makefile
## -- Release Commands --

release: ## Release agntrick package (usage: make release VERSION=1.0.0-alpha)
	@if [ -z "$(VERSION)" ]; then echo "Error: VERSION is required (e.g., VERSION=1.0.0-alpha)"; exit 1; fi
	@./scripts/release.sh $(VERSION)
```

Also update line 1 (`.PHONY`) to remove `release-whatsapp release-both`:

Replace:
```
.PHONY: help install run test clean format check docker-build docker-clean build build-clean release release-whatsapp release-both
```

with:
```
.PHONY: help install run test clean format check docker-build docker-clean build build-clean release
```

- [ ] **Step 2: Verify Makefile parses correctly**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && make help
```

Expected: Help output printed, no errors. `release-whatsapp` and `release-both` should NOT appear.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "chore: remove WhatsApp release targets from Makefile"
```

---

### Task 4: Clean up GitHub Actions release workflow

**Files:**
- Rewrite: `.github/workflows/release.yml`

**Why:** Remove all `publish-whatsapp-*` jobs. The remaining two jobs (`publish-pypi` for stable, `publish-testpypi` for pre-releases) are all that's needed. The trigger already works: GitHub releases created with `--prerelease` flag will trigger the `publish-testpypi` job.

- [ ] **Step 1: Rewrite `.github/workflows/release.yml`**

Replace the entire contents of `.github/workflows/release.yml` with:

```yaml
name: Release
on:
  release:
    types: [published]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  publish-pypi:
    runs-on: ubuntu-latest
    if: "!github.event.release.prerelease"
    environment:
      name: pypi
      url: https://pypi.org/p/agntrick
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
      - name: Build package
        run: uv build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

  publish-testpypi:
    runs-on: ubuntu-latest
    if: "github.event.release.prerelease"
    environment:
      name: testpypi
      url: https://test.pypi.org/p/agntrick
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
      - name: Build package
        run: uv build
      - name: Publish to TestPyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
```

Key changes:
- Removed all 4 WhatsApp jobs
- Simplified to 2 jobs: `publish-pypi` (stable) and `publish-testpypi` (pre-release)
- Uses `github.event.release.prerelease` to route -- this is set automatically by `gh release create --prerelease`
- Uses `uv build` directly instead of `make build` (fewer dependencies)
- Pinned action versions to stable major tags (`@v4`, `@v5`)

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "chore: simplify release workflow to single agntrick package"
```

---

### Task 5: Verify the build produces a correct distribution

**Files:** None (verification only)

**Why:** Before any release, confirm that `uv build` produces a wheel/sdist that includes the prompt files and has the correct version.

- [ ] **Step 1: Build the distribution**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && rm -rf dist/ && uv build
```

Expected: `dist/` contains `.whl` and `.tar.gz` files.

- [ ] **Step 2: Verify prompt files are in the wheel**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && python3 -c "
import zipfile, glob
whl = glob.glob('dist/*.whl')[0]
with zipfile.ZipFile(whl) as z:
    prompts = [n for n in z.namelist() if 'prompts/' in n and n.endswith('.md')]
    print(f'Found {len(prompts)} prompt files:')
    for p in prompts:
        print(f'  {p}')
    assert len(prompts) >= 7, f'Expected >= 7 prompt files, got {len(prompts)}'
    print('OK: prompt files included')
"
```

Expected: `OK: prompt files included` with 7+ files listed.

- [ ] **Step 3: Verify version in the wheel metadata**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && python3 -c "
import zipfile, glob
whl = glob.glob('dist/*.whl')[0]
with zipfile.ZipFile(whl) as z:
    metadata_files = [n for n in z.namelist() if n.endswith('METADATA')]
    with z.open(metadata_files[0]) as f:
        for line in f:
            decoded = line.decode().strip()
            if decoded.startswith('Version:'):
                print(decoded)
                assert '1.0.0' in decoded, f'Unexpected version: {decoded}'
                print('OK: version correct in wheel')
                break
"
```

Expected: `Version: 1.0.0-alpha` and `OK: version correct in wheel`.

- [ ] **Step 4: Clean up**

Run:
```bash
rm -rf dist/
```

---

### Task 6: Test the full release flow (dry-run)

**Files:** None (verification only)

**Why:** Do a dry-run of the release script to make sure it works end-to-end without actually pushing. This catches issues before the real release.

- [ ] **Step 1: Run release script with an invalid version to test validation**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && bash scripts/release.sh "not-a-version" 2>&1 | head -3
```

Expected: `[ERROR] Invalid version: 'not-a-version'`

- [ ] **Step 2: Run release script with a valid pre-release version (it will fail at clean check since we have commits, that's OK)**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && bash scripts/release.sh "1.0.0-alpha" 2>&1 | head -5
```

Expected: Either succeeds (if you committed everything) or fails at `Uncommitted changes` check (which proves the safety check works). If it fails at clean check, that's the correct behavior.

- [ ] **Step 3: Verify the script is syntactically valid with bash**

Run:
```bash
bash -n scripts/release.sh && echo "Syntax OK"
```

Expected: `Syntax OK`

---

### Task 7: Final commit and prepare for actual release

**Files:** None (summary only)

**Why:** At this point all changes are committed. The project is ready for its first real release via `make release VERSION=1.0.0-alpha`.

- [ ] **Step 1: Run full check and test suite**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && make check && make test
```

Expected: All checks pass, all tests pass.

- [ ] **Step 2: Verify git log shows all commits**

Run:
```bash
cd /Users/jeancsil/code/agents/.worktrees/whatsapp-api && git log --oneline -10
```

Expected: See the commits from Tasks 1-4 in the log.

- [ ] **Step 3: Merge to main and release**

Once this branch is merged to main, run:

```bash
# Pre-release to TestPyPI:
make release VERSION=1.0.0-alpha

# Or stable to PyPI (after testing the alpha):
make release VERSION=1.0.0
```

---

## DigitalOcean Deployment (reference)

After `1.0.0` is published to PyPI, deploy on your Ubuntu x86_64 droplet:

```bash
# Option A: Docker (recommended - includes Go gateway)
git clone https://github.com/jeancsil/agntrick.git
cd agntrick
cp .env.example .env  # edit with your keys
docker compose up -d

# Option B: pip install (Python only, no Go gateway)
pip install agntrick
agntrick serve  # starts FastAPI on port 8000
# You'd need to compile the Go gateway separately for WhatsApp
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Every issue from the analysis is addressed (version sync, release script, CI cleanup, build verification)
- [x] **No placeholders:** Every step has exact code, commands, and expected output
- [x] **Type consistency:** `__version__` uses string everywhere, `version` in toml is string, no type mismatch
- [x] **No TDD:** User explicitly said no TDD needed -- tests only verify build artifacts, not new unit tests
