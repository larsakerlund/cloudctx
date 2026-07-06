# cloudctx self-update — git is the update channel

**Status:** approved design
**Date:** 2026-07-06

## 1. Objective

Users update with one command instead of remembering the install location and
pulling by hand. No packaging, no installer infrastructure: the install IS a
git clone (binary symlinked from it), so git is the update channel and tags
(`vX.Y.Z`) are the versioning.

## 2. Behavior

### `cloudctx self-update`

1. Install dir = `script_dir()` (symlink already resolved by `__file__`).
   Not a git clone → clean error telling the user to update the way they
   installed.
2. Dirty working tree (`git status --porcelain`) → refuse with guidance.
   Never stash or discard someone's local edits.
3. `git pull --ff-only` (120s timeout). Failure → error with git's output.
   HEAD unchanged → "already up to date (<version>)".
4. On update: run the **new** binary (`sys.executable <bin> --version` and
   `... gen-profiles`) so the version reported and the regenerated iTerm2
   profiles come from the new code, not the still-running old process.
   Profile regen failure is tolerated (non-mac).
5. Print `updated: <old> -> <new> (<sha> -> <sha>)` and remind the user to
   open a new shell to pick up the shim.

### `cloudctx self-update --check`

Passive, explicit-only (no command ever phones home on its own):
`git ls-remote --tags origin`, parse `vX.Y.Z` tags, semver-compare the max
against `__version__`. Prints "update available: a -> b" or "up to date".
Uses the clone's own remote and the user's existing git auth — works for any
remote host, no HTTP client, no API parsing.

## 3. Constraints

- Stdlib only; all subprocesses timeout-guarded (never hang a shell).
- Tests are hermetic: a local fixture remote (git init + copy of the real CLI
  file + tags), cloned to a fixture install dir; `script_dir` monkeypatched.
  No network.
- Version bumps to 1.2.0. Completion lists gain `self-update`.

## 4. Out of scope

Homebrew tap / PyPI (revisit when there are external users), auto-checks on
normal commands (telemetry stance), updating live shells (impossible from a
child process — the reminder is the honest UX).
