---
name: deploy-do
description: Deploy a git branch to the DigitalOcean droplet. Use this skill whenever the user wants to deploy, push to production, ship to DO, update the server, or mentions the droplet/production environment. Also triggers on "deploy this branch", "push to DO", "ship it", "update the server", "what's running on the droplet", "check the server", or "restart the API". Even casual mentions like "let's get this live" or "put this on the server" should trigger this skill.
---

# Deploy to DigitalOcean

Deploy the current branch to the DO droplet, restart services, and verify everything is healthy.

## Connection Details

The droplet SSH connection is configured via env vars (sourced from `~/Dev/dotfiles/configs/5_do_droplet.on.zsh` in zsh):

- `DO_SSH_KEY` — path to the SSH private key
- `DO_HOST` — droplet IP address
- `DO_USER` — SSH user
- `DO_PROJECT_PATH` — agntrick project directory on the droplet

All remote commands use this pattern. The `-o ConnectTimeout=10` ensures SSH fails fast if the droplet is unreachable:

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" "cd $DO_PROJECT_PATH && <command>"
```

**Health endpoint:** `http://localhost:8000/health`

**If env vars are not set**, remind the user to source the config: `source ~/Dev/dotfiles/configs/5_do_droplet.on.zsh`

## Deployment Steps

### 1. Confirm the deployment

Before doing anything, confirm with the user:

```
Deploy branch <branch> to DO droplet ($DO_HOST)?
```

Use `git branch --show-current` to detect the current branch. If the user specified a branch, use that instead.

### 2. Push the branch to remote

Ensure the branch is pushed so the droplet can pull it:

```bash
git push origin <branch>
```

If the push fails (e.g., no remote tracking branch), ask the user how to proceed before continuing.

### 3. Fetch and checkout on the droplet

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "cd $DO_PROJECT_PATH && git fetch origin && git checkout <branch> && git pull origin <branch>"
```

If `git checkout` fails because of uncommitted changes on the droplet, stash them, retry, then restore:

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "cd $DO_PROJECT_PATH && git stash && git checkout <branch> && git pull origin <branch> && git stash pop"
```

Mention to the user that stashed changes were restored. If `git stash pop` produces conflicts, report them and ask how to proceed.

### 4. Build dependencies

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "cd $DO_PROJECT_PATH && bash scripts/deploy.sh build"
```

This runs `uv sync` and `go build` for the gateway. It also installs Playwright Chromium if missing (non-fatal).

### 5. Restart all services

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "cd $DO_PROJECT_PATH && bash scripts/deploy.sh restart"
```

This stops the toolbox, API, and gateway, then starts them fresh. It waits for each service to be ready (toolbox ~15s, API ~30s).

### 6. Verify health

Wait a moment for the API to fully initialize, then check:

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "curl -sf http://localhost:8000/health"
```

If this returns a non-zero exit code or doesn't respond within ~30s, the deploy failed. Report the issue and show the logs (step 7).

### 7. Check logs for errors

Search the recent logs for error signatures:

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "grep -E 'ERROR|CRITICAL|Traceback|ImportError|ModuleNotFoundError' ~/.local/share/agntrick/logs/api-agntrick.log | tail -20"
```

Also check that startup completed:

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "tail -5 ~/.local/share/agntrick/logs/api-agntrick.log"
```

Look for:
- `ERROR` or `CRITICAL` lines
- Stack traces or tracebacks
- `ModuleNotFoundError` or `ImportError` (wiring issues)
- Repeated connection failures

### 8. Report result

**On success:**
```
Deployed <branch> to DO droplet successfully.
- Services: toolbox, API, gateway all running
- Health: OK
- Logs: clean (no errors)
```

**On failure:**
```
Deploy of <branch> FAILED.
- Step that failed: <step>
- Error: <error output>
- Logs: <relevant log lines>
```

Show the error output and log lines so the user can diagnose. Do not attempt rollback automatically.

## After Merge

When a feature branch is merged to main, deploy main to the droplet to reset it from the feature branch:

```bash
git checkout main && git pull origin main
```

Then follow steps 2–8 with `main` as the branch.

## Variations

### Quick restart (no code changes)

If the user just wants to restart services without pulling new code:

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "cd $DO_PROJECT_PATH && bash scripts/deploy.sh restart"
```

Then verify health and check logs (steps 6–7).

### Check status only

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "cd $DO_PROJECT_PATH && bash scripts/deploy.sh status"
```

### Tail live logs

```bash
ssh -o ConnectTimeout=10 -i "$DO_SSH_KEY" "$DO_USER@$DO_HOST" \
  "cd $DO_PROJECT_PATH && bash scripts/deploy.sh logs"
```

This is interactive (follows log output). Only use when the user asks to watch logs.

## Notes

- The deploy script handles the toolbox (MCP), API (FastAPI), and gateway (Go WhatsApp). All three are restarted.
- The droplet has 1GB RAM. Build steps (especially Playwright) can be slow or fail due to memory. If `uv sync` fails, suggest the user check disk/memory on the droplet.
- The `build` step also pulls the agntrick-toolkit repo at `~/agntrick-toolkit`. This is separate from the main project.
