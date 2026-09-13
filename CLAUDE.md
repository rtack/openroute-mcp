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

As of 2026-09-13: `origin/main` and local `main` are identical, sitting two
commits ahead of `upstream/main` — `cacb029` (fork-only SDK-pin fix, not yet
sent upstream) and this `CLAUDE.md`'s own addition (a fork-only doc commit,
staying on `main`/`origin` rather than moving to `local-dev` — see the
Branching section above for why this repo can't push a true "pure mirror"
`main`).

## Worktree Isolation Required for All Work

Per the standing rule (global CLAUDE.md), all edits/commits here go
through an isolated git worktree, never directly in this shared checkout —
use `EnterWorktree` before editing any file. This repo has no daemon and
no other concurrently-active session today, but the convention is applied
uniformly so a future concurrent session (or a future daemon-style
architecture) never inherits an uncommitted change left in the shared
checkout by mistake.

## Branching & terminology: "deploy" vs PR

**Deliberate deviation from google-mcp's three-branch model — `main` is not,
and cannot be, a pure upstream mirror here.** Elsewhere, `local-dev` exists
so `main` can stay a pure, cleanly-fast-forwardable copy of `upstream/main`
while local-only work accumulates elsewhere. That reasoning is orthogonal to
daemon-vs-stdio architecture (a mistake made and corrected on several other
repos 2026-09-13) — but here it runs into a *different*, genuinely
structural constraint: `uvx` resolves against `origin`'s default branch
(`main`) directly, with no separate build/deploy step to promote anything
onto it (see mechanics above). If `main` were reset to a bare
`upstream/main` mirror, the live tool would lose `cacb029` (the SDK-pin fix
that keeps it working at all) the next reconnect. So `main` here plays a
dual role — nominally the default branch, but functionally the thing other
repos call `local-dev` — and there is no separate "pure mirror" branch to
match `upstream/main` against with a plain `diff`.

- **`main`** — the fork's default branch *and* the actual deploy target.
  Normally `upstream/main` plus any fork-only patches not yet sent upstream
  (currently just `cacb029`). Kept in sync with `origin/main` (push
  immediately after any local `main` change).
- **`local-dev`** — exists for workflow parity with every other repo
  (`feat/<name>` branches are cut from here, not `main`), **not** for the
  "never pushed, keeps main pure" guarantee those repos have — that
  guarantee is structurally unavailable here. In practice `local-dev` and
  `main` are usually the same commit; `local-dev` only gets ahead of `main`
  during in-progress work not yet ready to deploy.
- **`feat/<name>`** — one per feature/fix, branched from `local-dev` inside
  a worktree, pushed to `origin` once ready.
- **"Deploy"** = merge a `feat/<name>` branch into `local-dev`, fast-forward
  `local-dev` into `main` (`git checkout main && git merge --ff-only
  local-dev`), and `git push origin main`. That alone makes the change live
  for the *next* MCP reconnect (see mechanics above) — no daemon restart, no
  rebuild step. Gate: tests/lint clean (see Testing below); no code review
  required for pushing to Raphael's own fork.
- **PR** = a GitHub pull request opened against `vemonet/openroute-mcp`
  (the upstream project), from the `feat/<name>` branch directly. Gate:
  everything a deploy requires, plus code review (e.g. `/code-review` on
  the branch diff) and the `pr-approval-gate` skill's fresh, explicit,
  in-the-moment approval — never open one preemptively "since it seems
  like the obvious next step."

### Sync with upstream before starting branch work

```bash
git fetch upstream main
git log --oneline main..upstream/main   # anything printed means it moved
```

If it moved: rebase `main` onto the new `upstream/main` (`git rebase
upstream/main` from `main` — replays `main`'s fork-only commits like
`cacb029` on top; there's no clean fast-forward here since `main` always
carries at least those fork-only patches, unlike the pure-mirror repos),
push the rebased `main` to `origin` (`git push origin main --force-with-lease`
— a rebase always requires this, not a plain push), then rebase `local-dev`
onto the updated `main` too.

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
