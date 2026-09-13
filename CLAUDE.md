# CLAUDE.md

This file provides guidance to Claude Code when working with code in this
repository.

## What this repo is

`rtack/openroute-mcp` is Raphael's fork of
[`vemonet/openroute-mcp`](https://github.com/vemonet/openroute-mcp) — an
MCP server wrapping the OpenRouteService API (route planning, geocoding,
reachability/isochrones, POI search) for activities like hiking or
mountain biking. It is **not** an original project — it has a real
upstream maintainer, so the fork/upstream/PR conventions below apply, same
as `~/dev/ai/google-mcp`.

## Unusual live registration — read this before assuming the local checkout is "the" server

Unlike `google-mcp` (a pooled daemon process built from a local checkout and
supervised by a LaunchAgent), this MCP server has **no locally-running
process at all** between sessions. The live registration
(`~/.claude.json` → `mcpServers.openroute`) is:

```json
{
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "git+https://github.com/rtack/openroute-mcp", "openroute-mcp"],
  "env": { "OPENROUTESERVICE_API_KEY": "…" }
}
```

Every time a Claude Code session (re)connects the `openroute` MCP server,
it spawns `uvx --from git+https://github.com/rtack/openroute-mcp
openroute-mcp` fresh. This local checkout at
`~/dev/ai/openroute-mcp` is a normal git working copy for editing and
committing — **editing files here has zero live effect until pushed to
`origin` and the MCP connection is respawned.** There is no `pnpm build` /
daemon-restart step like `google-mcp` has; the "build" is just `git push`.

### Verified fetch/cache mechanics (checked 2026-09-13 with `uvx -v`)

Running `uvx -v --from git+https://github.com/rtack/openroute-mcp
openroute-mcp` shows, on **every** invocation:

```
DEBUG Fetching source distribution from Git: https://github.com/rtack/openroute-mcp
DEBUG Updating Git source `https://github.com/rtack/openroute-mcp`
DEBUG Performing a Git fetch for: https://github.com/rtack/openroute-mcp
...
DEBUG Searching for a compatible version of openroute-mcp @ git+https://github.com/rtack/openroute-mcp (*)
```

Because the registration pins no ref (no `@<branch>`/`@<tag>`/`@<sha>`),
`uv` resolves against the default branch (`main`) and **performs a live
`git fetch` against `origin` (GitHub) on every single spawn** — it does not
trust a stale cached resolution. It then reuses cached build artifacts
keyed by the exact resolved commit SHA
(`~/.cache/uv/git-v0/checkouts/<hash>/<short-sha>/…`) so a repeat of the
*same* commit is fast, but a new commit on `origin/main` is always
detected and fetched.

**Practical consequence: a normal push-and-reconnect cycle needs no cache
clearing and no `uv cache clean` / `uvx --refresh`.** To make a code change
live:

1. Commit and push the change to `origin` (this fork — `git push origin
   main` or merge a feature branch into `main` and push that).
2. Reconnect the MCP server: `/exit`, then `claude --resume` (pick the
   session from the picker) — this respawns all MCP server subprocesses,
   including a fresh `uvx` invocation that will git-fetch the just-pushed
   commit. See the `mcp-reconnect` skill for why `--resume` (not `-c`) is
   the right form.

`--refresh`/cache-clearing would only matter if a ref were ever pinned to a
specific tag/sha in the registration (not the case today) or if uv's own
git-fetch step itself were suspected of being skipped — to sanity-check
that, rerun `uvx -v --from git+https://github.com/rtack/openroute-mcp
openroute-mcp <cmd> 2>&1 | grep -i "git fetch"` and confirm the resolved
commit (visible a few lines later, e.g. `.../raw/<sha>/pyproject.toml`)
matches `git -C ~/dev/ai/openroute-mcp rev-parse origin/main`.

## Remotes (confirmed 2026-09-13)

```
origin    https://github.com/rtack/openroute-mcp.git   (fetch/push) — Raphael's fork, what uvx pulls from live
upstream  https://github.com/vemonet/openroute-mcp.git (fetch/push) — the original project
```

Both already correctly configured — no setup needed. `gh repo view
rtack/openroute-mcp --json parent` confirms `isFork: true`,
`parent: vemonet/openroute-mcp`.

As of 2026-09-13: `origin/main` and local `main` are identical, and both
sit exactly one commit ahead of `upstream/main`
(`cacb029 fix: pin mcp SDK below v2 to avoid breaking fastmcp rework`) — a
fork-only fix not yet sent upstream.

## Worktree Isolation Required for All Work

Per the standing rule (global CLAUDE.md), all edits/commits here go
through an isolated git worktree, never directly in this shared checkout —
use `EnterWorktree` before editing any file. This repo has no daemon and
no other concurrently-active session today, but the convention is applied
uniformly so a future concurrent session (or a future daemon-style
architecture) never inherits an uncommitted change left in the shared
checkout by mistake.

## Branching & terminology: "deploy" vs PR

Simpler than `google-mcp` — there is no `local-dev` integration branch and
no separate build/daemon-restart step, because "the live server" *is*
whatever commit sits on `origin/main` (see mechanics above).

- **`main`** — normally a mirror of `upstream/main` plus any fork-only
  patches not yet sent upstream (currently just `cacb029`). Kept in sync
  with `origin/main` (push immediately after any local `main` change —
  there's no separate fork-sync step to forget, unlike `google-mcp`'s
  three-branch model).
- **`feat/<name>`** — one per feature/fix, branched from `main` inside a
  worktree, pushed to `origin` once ready.
- **"Deploy"** = merge a `feat/<name>` branch into `main` and `git push
  origin main`. That alone makes the change live for the *next* MCP
  reconnect (see mechanics above) — no daemon restart, no rebuild step.
  Gate: tests/lint clean (see Testing below); no code review required for
  pushing to Raphael's own fork.
- **PR** = a GitHub pull request opened against `vemonet/openroute-mcp`
  (the upstream project), for a fix/feature worth sending back. Gate:
  everything a deploy requires, plus code review (e.g. `/code-review` on
  the branch diff) and the `pr-approval-gate` skill's fresh, explicit,
  in-the-moment approval — never open one preemptively "since it seems
  like the obvious next step."

### Sync with upstream before starting branch work

```bash
git fetch upstream main
git log --oneline main..upstream/main   # anything printed means it moved
```

If it moved: fast-forward local `main`
(`git update-ref refs/heads/main refs/remotes/upstream/main` — safe as
long as `main` carries no unpushed fork-only commits beyond what's already
on `origin`) and push to `origin` (`git push origin main`) so the fork's
GitHub `main` — the thing `uvx` actually resolves against — doesn't go
stale relative to what Raphael thinks is current.

## Testing & Linting (verified 2026-09-13, real commands actually run)

Install dev dependencies first: `uv sync --group dev`.

```bash
uv run pytest        # tests
uv run ruff check .  # lint
uv run mypy          # type check (strict = true in pyproject.toml)
```

Verified output:

- `uv run ruff check .` → `All checks passed!`
- `uv run mypy` → `Success: no issues found in 4 source files`
- `uv run pytest` → **requires `OPENROUTESERVICE_API_KEY` set in the
  environment.** The one test
  (`tests/test_openrouteservice.py::test_search_location_coordinates`)
  makes a real network call to `api.openrouteservice.org`'s geocode
  endpoint; without a key it fails with `httpx.HTTPStatusError: 401
  Unauthorized` (empty `api_key=`), not a code bug. With the same key
  used in the live MCP registration
  (`~/.claude.json` → `mcpServers.openroute.env.OPENROUTESERVICE_API_KEY`)
  exported into the shell, it passes: `1 passed in 1.07s`. Don't hardcode
  that key into the repo — export it locally when running tests.

`.pre-commit-config.yaml` additionally runs `ruff` (`--fix`) + `ruff-format`
+ basic hygiene hooks (large files, TOML/YAML validity, trailing
whitespace, EOF newline) on commit; its `mypy` hook is present but
commented out, so `uv run mypy` above is the only place type-checking
actually runs — run it manually, don't rely on pre-commit for it.
