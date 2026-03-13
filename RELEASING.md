# Releasing Agntrick Packages

This document describes how to release new versions of `agntrick` and `agntrick-whatsapp` packages to PyPI.

## Overview

Agntrick uses a monorepo structure with two independently versioned packages:

- **agntrick** (v0.2.8): Core framework
- **agntrick-whatsapp** (v0.3.3): WhatsApp integration

Each package can be released independently, allowing different release cadences for core features and platform-specific integrations.

## Prerequisites

### 1. Trusted Publishers (One-time setup)

Agntrick uses PyPI's [Trusted Publishers](https://docs.pypi.org/trusted-publishers/) for secure, OIDC-based authentication. No API tokens or passwords are stored in GitHub.

**Configure for `agntrick`:**

1. Go to https://pypi.org/manage/project/agntrick/settings/publishing/
2. Click "Add a new pending publisher"
3. Configure:
   - **PyPI Project Name:** `agntrick`
   - **Owner:** `jeancsil`
   - **Repository name:** `agntrick`
   - **Workflow name:** `.github/workflows/release.yml`
   - **Environment name:** `pypi` (or leave blank)

**Configure for `agntrick-whatsapp`:**

1. Go to https://pypi.org/manage/project/agntrick-whatsapp/settings/publishing/
2. Configure the same settings as above

### 2. Permissions

- You must have `push` access to the repository
- You must be a maintainer/owner of PyPI projects
- **You must be on the `main` branch** (or use `FORCE_RELEASE=1` to bypass)

### 3. GitHub CLI

The automated release requires GitHub CLI (`gh`) installed and authenticated:

```bash
brew install gh        # macOS
# OR
apt install gh         # Linux

gh auth login
```

## Automated Release (Recommended)

Use the `make` commands for streamlined releases:

### Release Core Package Only

```bash
make release VERSION=0.3.0
```

This releases `agntrick` to version 0.3.0 and:
- Updates `pyproject.toml` version
- Runs all tests
- Commits, tags, and pushes to GitHub
- Creates GitHub release (triggers PyPI publish)

### Release WhatsApp Package Only

```bash
make release-whatsapp VERSION=0.4.0
```

This releases `agntrick-whatsapp` to version 0.4.0 independently.

### Release Both Packages

```bash
make release-both CORE=0.3.0 WHATSAPP=0.4.0
```

This releases both packages with different versions:
- agntrick → v0.3.0
- agntrick-whatsapp → v0.4.0

When releasing both, the WhatsApp package's dependency on `agntrick` is automatically updated to `agntrick>=0.3.0`.

## Manual Release (Without make command)

If you need more control, you can manually execute the release script:

```bash
# Release agntrick
./scripts/release.sh agntrick 0.3.0

# Release agntrick-whatsapp
./scripts/release.sh agntrick-whatsapp 0.4.0

# Release both
./scripts/release.sh both 0.3.0 0.4.0
```

## Step-by-Step Manual Release

If you prefer manual control over each step:

### Step 1: Ensure main is up to date

```bash
git checkout main
git pull origin main
```

### Step 2: Verify all checks pass

```bash
make check
make test
```

### Step 3: Update version number

Edit `pyproject.toml` and update the `version` field:

```toml
version = "0.3.0"  # Update this
```

Also update `packages/agntrick-whatsapp/pyproject.toml` if the WhatsApp package changed.

### Step 4: Commit and push

```bash
git add pyproject.toml packages/agntrick-whatsapp/pyproject.toml
git commit -m "chore: bump version to 0.3.0"
git push origin main
```

### Step 5: Create a GitHub Release

```bash
gh release create v0.3.0 --title "v0.3.0" --notes "Release notes here"
```

Or use the GitHub UI:
1. Go to https://github.com/jeancsil/agntrick/releases/new
2. Tag: `v0.3.0`
3. Title: `v0.3.0`
4. Add release notes
5. Click "Publish release"

## Version Strategy

### Independent Versioning

Each package has its own version number:

| Package | Current Version | Tag Format |
|---------|----------------|-------------|
| agntrick | 0.2.8 | `vX.Y.Z` |
| agntrick-whatsapp | 0.3.3 | `agntrick-whatsapp-vX.Y.Z` |

### Semantic Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features, backward compatible
- **PATCH** (0.0.X): Bug fixes

### When to Bump Which Version

| Scenario | agntrick | agntrick-whatsapp | Command |
|----------|----------|-------------------|----------|
| Core bug fix | Patch | No change | `make release VERSION=x.y.z` |
| Core new feature | Minor | No change | `make release VERSION=x.y.0` |
| Core breaking change | Major | Update dependency, bump | `make release-both` |
| WhatsApp-only fix | No change | Patch | `make release-whatsapp VERSION=x.y.z` |
| WhatsApp new feature | No change | Minor | `make release-whatsapp VERSION=x.y.0` |
| Both packages | Bump both | Bump both | `make release-both` |

## What Happens Next

The [release workflow](.github/workflows/release.yml) automatically:

1. **Builds** the packages (`agntrick` and `agntrick-whatsapp`)
2. **Publishes to PyPI** (for full releases)
3. **Publishes to TestPyPI** (for pre-releases)

### For Full Releases

- Packages are published to https://pypi.org/project/agntrick/
- Users can install with `pip install agntrick`

### For Pre-releases

Create a pre-release by marking the GitHub release as "pre-release":
- Packages go to https://test.pypi.org/project/agntrick/
- Install with `pip install -i https://test.pypi.org/simple/ agntrick`

## Verification

### Verify Release on PyPI

After the GitHub Actions workflow completes:

```bash
# Check agntrick
curl -s https://pypi.org/pypi/agntrick/json | jq -r '.info.version'

# Check agntrick-whatsapp
curl -s https://pypi.org/pypi/agntrick-whatsapp/json | jq -r '.info.version'
```

### Test Install Fresh Version

```bash
# Test install
uv pip install --force-reinstall agntrick==0.3.0
uv pip install --force-reinstall agntrick-whatsapp==0.4.0
```

## Troubleshooting

### "Uncommitted changes detected"

Commit or stash your changes before releasing:

```bash
git status
git commit -am "WIP"
# OR
git stash
```

### "Invalid version format"

Versions must follow semantic versioning: `X.Y.Z`

```bash
# Correct
make release VERSION=0.3.0

# Incorrect
make release VERSION=0.3       # Missing patch
make release VERSION=0.3.0.1    # Too many parts
make release VERSION=v0.3.0     # No 'v' prefix
```

### "Tests failed. Aborting release"

Fix test failures before releasing:

```bash
make check && make test
# Fix issues, then retry release
```

### "You are on branch 'X', but releases should be done from 'main'"

The release script checks that you're on the `main` branch before releasing. This prevents accidental releases from feature branches.

**To fix:**

```bash
# Switch to main branch
git checkout main
git pull origin main

# Then try release again
make release VERSION=0.3.0
```

**To bypass this check (not recommended):**

```bash
# Only use this if you know what you're doing
FORCE_RELEASE=1 make release VERSION=0.3.0
```

### "GitHub CLI (gh) is required"

Install and authenticate gh:

```bash
brew install gh  # macOS
# OR
apt install gh  # Linux

gh auth login
```

### Release failed with "400 Bad Request"

This usually means the Trusted Publisher isn't configured:

1. Verify publisher settings on PyPI match exactly:
   - Repository name (case-sensitive)
   - Workflow name (including `.yml` extension)
   - Environment name (if used)

### Package already exists

You cannot republish the same version. Increment the version number and try again.

### Build fails

Run locally to debug:

```bash
make build
ls -la dist/
```

### Tests fail in CI but pass locally

Ensure your `.env` has the required API keys for testing:
```bash
export OPENAI_API_KEY=sk-test  # For CI
```

### Rollback

PyPI does not allow overwriting existing versions. If something goes wrong:

1. Delete the GitHub release
2. Delete the git tag (locally and remotely)
3. Increment version to a new number
4. Create new release

```bash
# Delete remote tag
git push origin --delete v0.3.0

# Delete local tag
git tag -d v0.3.0

# Release with new version
make release VERSION=0.3.1
```

## Manual Publishing (Emergency Only)

If GitHub Actions is unavailable, you can publish manually:

```bash
# Build
make build

# Publish to PyPI (requires API token)
uv run twine upload dist/*
```

Note: Manual publishing requires a PyPI API token, which is less secure than Trusted Publishers.

## Quick Reference

```bash
# View current versions
grep "^version" pyproject.toml
grep "^version" packages/agntrick-whatsapp/pyproject.toml

# View recent tags
git tag -l --sort=-version:refname

# Run full check before release
make check && make test

# Automated release commands
make release VERSION=0.3.0
make release-whatsapp VERSION=0.4.0
make release-both CORE=0.3.0 WHATSAPP=0.4.0

# Manual script commands
./scripts/release.sh agntrick 0.3.0
./scripts/release.sh agntrick-whatsapp 0.4.0
./scripts/release.sh both 0.3.0 0.4.0
```
