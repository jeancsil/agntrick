# Releasing Agntrick

This document describes how to release new versions of Agntrick to PyPI.

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
- You must be a maintainer/owner of the PyPI projects

## Release Process

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

## Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features, backward compatible
- **PATCH** (0.0.X): Bug fixes

## Troubleshooting

### Release failed with "400 Bad Request"

This usually means the Trusted Publisher isn't configured:

1. Verify the publisher settings on PyPI match exactly:
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

## Manual Publishing (Emergency Only)

If GitHub Actions is unavailable, you can publish manually:

```bash
# Build
make build

# Publish to PyPI (requires API token)
uv run twine upload dist/*
```

Note: Manual publishing requires a PyPI API token, which is less secure than Trusted Publishers.
