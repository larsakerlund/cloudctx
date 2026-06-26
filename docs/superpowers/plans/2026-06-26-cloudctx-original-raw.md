# cloudctx: per-window Azure / AWS CLI context isolation

> **Provenance note (added 2026-06-26):** This is the *original, pre-refinement*
> plan. It is preserved here for history. It has been **superseded** by the
> approved design spec (`../specs/2026-06-26-cloudctx-design.md`) and the
> bite-sized TDD plan (`2026-06-26-cloudctx.md`), which deliberately deviate on
> two points:
>
> 1. **Packaging:** Typer → zero-dependency single-file `argparse` CLI. The build
>    machine is Python 3.9.6 with no pipx/uv/poetry, and `ctx use` runs on every
>    shell startup, so cold-start latency and zero-install matter. (`tomllib` is
>    3.11+ and read-only, so reading falls back to a mini-parser and writing is
>    hand-rolled.)
> 2. **AWS auth automation deferred to a later version.** The AWS CLI is not
>    installed on the build machine. The `contexts.toml` schema keeps all `aws_*`
>    fields and the env exports are AWS-ready, but `new`/`login` only automate
>    Azure in v1; AWS auth is a clear "not yet implemented" stub. This makes the
>    original's one open question (SSO vs static-keys vs assume-role) moot for v1.

A plan for Claude Code to implement. The goal is rambox-style isolation: several
Azure and AWS CLI identities authenticated at the same time across separate
iTerm2 windows, with no window ever silently swapping context because another
window logged in to a different customer tenant.

## 1. Objective

Let one machine hold many live cloud identities concurrently. Each iTerm2 window
(and any Claude Code session launched inside it) is pinned to exactly one named
context. Authenticating or switching subscription in one window must have zero
effect on any other window.

## 2. Root cause to design around

- Azure CLI stores active state in one directory, `$AZURE_CONFIG_DIR`
  (default `$HOME/.azure`). `azureProfile.json` records which subscription is
  active; `msal_token_cache.json` holds tokens. All windows share this directory,
  so `az login` or `az account set` in one window changes the active subscription
  for every window.
- AWS CLI has no active-profile file. Resolution order is the `--profile` flag,
  then `AWS_PROFILE`, then the `default` profile. The SSO token cache under
  `$HOME/.aws/sso/cache` is keyed per session, so multiple SSO logins coexist.
  AWS only bleeds when something writes the `default` profile or when code relies
  on `default`.

The fix for both: point each shell at its own credential files through
environment variables, set before any `az` or `aws` command runs.

## 3. Core design principle

A context is a self-contained credential bundle. Selecting a context exports a
fixed set of environment variables into the current shell:

```
AZURE_CONFIG_DIR             -> per-context Azure config + token cache
AWS_CONFIG_FILE              -> per-context AWS config
AWS_SHARED_CREDENTIALS_FILE  -> per-context AWS credentials (static keys, if any)
AWS_PROFILE                  -> the profile name to use within that config
```

Because the active Azure subscription lives inside `AZURE_CONFIG_DIR`, and AWS
selection is driven by these env vars, two windows with different exports cannot
interfere. Re-login in one is invisible to the other. This is the property to
verify in testing.

Note on the AWS SSO cache: it stays at `$HOME/.aws/sso/cache` and is shared
across contexts. That is safe because entries are keyed by the SSO session start
URL, so different customers do not collide. Do not try to relocate it; AWS has no
supported env var for that path.

## 4. Context abstraction and on-disk layout

Root: `$HOME/.cloudctx`

```
$HOME/.cloudctx/
  contexts.toml                # registry of all contexts
  <name>/
    azure/                     # used as AZURE_CONFIG_DIR
    aws/
      config                   # used as AWS_CONFIG_FILE
      credentials              # used as AWS_SHARED_CREDENTIALS_FILE
```

`contexts.toml` entry per context:

```toml
[acme]
display    = "Acme AB"
color      = "#c0392b"        # iTerm2 tab/badge color
azure_tenant       = "<tenant-guid>"
azure_subscription = "<sub-guid-or-name>"   # the one to select after login
aws_sso_start_url  = "https://acme.awsapps.com/start"
aws_sso_region     = "eu-north-1"
aws_account_id     = "<account-id>"
aws_role           = "<permission-set>"
aws_profile        = "acme"   # value exported as AWS_PROFILE
```

The AWS auth fields should be optional. Support three AWS modes per context:
SSO (preferred), static access keys, and assume-role. A context may be
Azure-only or AWS-only.

## 5. The manager tool

### Hard constraint

`ctx use` must mutate the current shell's environment, so the entry point that
selects a context has to be a shell function that is sourced, not a separate
binary. A binary runs in a child process and cannot export into the parent shell.

Recommended split:

- A Python CLI (Typer) for everything that does not need to mutate the parent
  shell: `new`, `list`, `login`, `status`, `open`, registry edits, iTerm2 profile
  generation. This matches the existing AKS context manager stack.
- A thin sourced shell function `ctx` (zsh, with a bash variant) that:
  - for `use`, reads the context from the registry and runs `export` directly in
    the current shell, then emits the iTerm2 badge / title / color sequences;
  - for every other subcommand, delegates to the Python CLI.

A clean pattern: the Python CLI implements `ctx _env <name>` which prints the
`export` lines, and the shell function does `eval "$(cloudctx _env "$name")"`.
That keeps the env logic in one place while still mutating the parent shell.

### Command inventory

- `ctx list` lists contexts and marks which one is active in this shell.
- `ctx use <name>` exports env into the current shell, sets badge, title, tab color.
- `ctx new <name>` scaffolds the directory and registry entry, then runs guided
  first-time auth (see below).
- `ctx login <name>` re-authenticates the context into its isolated store
  (`az login` plus `aws sso login`), without requiring the shell to be in it.
- `ctx open <name>` launches a new iTerm2 window or tab already scoped to the
  context, optionally `cd` into a project and start `claude`.
- `ctx status` / `ctx whoami` shows the real identity for the current shell:
  `az account show` and `aws sts get-caller-identity`.
- `ctx exec <name> -- <cmd...>` runs a one-off command in a context by setting the
  env for that single invocation, leaving the shell unchanged.
- `ctx clear` unsets the exported vars in the current shell.

### First-time auth inside an isolated store

`ctx new` and `ctx login` must run the auth commands with the per-context env
already set, so tokens land in the isolated directory:

- Azure: `az login --tenant <azure_tenant>` then `az account set --subscription <azure_subscription>`.
- AWS SSO: write the SSO session and profile into the per-context `config`, then
  `aws sso login --profile <aws_profile>`.
- AWS static keys: write them into the per-context `credentials` file.

Refresh tokens then persist in the context directory and survive across windows
and reboots, so this is a once-per-context step.

## 6. iTerm2 integration

Three layers, increasing in polish:

1. Visible context indicator on `ctx use`. Emit iTerm2 escape sequences so the
   window shows which customer it is on:
   - Badge: print the iTerm2 SetBadgeFormat sequence with the base64 of the
     context display name.
   - Tab title: set via the title escape sequence.
   - Tab color: set per the context color so each customer is visually distinct,
     the way rambox colors each account.
   Claude Code should look up the exact current iTerm2 escape sequences rather
   than hardcoding from memory, then verify they render.

2. `ctx open <name>` launches a scoped window or tab. Use the iTerm2 Python API
   or AppleScript to open a new session, then send the `ctx use <name>` command
   (or inject the env) so the new window starts already pinned. Add a flag to also
   `cd` to a project path and run `claude`.

3. Dynamic profiles (optional convenience). Generate
   `$HOME/Library/Application Support/iTerm2/DynamicProfiles/cloudctx.json` with
   one profile per context, each carrying the context color and an initial command
   that runs `ctx use <name>`. This lets you pick a customer from the iTerm2
   profile menu and get a correctly scoped window without typing. The Python CLI
   should regenerate this file whenever the registry changes.

## 7. Prompt guardrails

The point of failure is acting in the wrong context, so make the active context
impossible to miss and add a guard:

- Prompt segment showing context name plus a short Azure subscription label plus
  `AWS_PROFILE`. Implement for zsh, and also emit a Starship custom segment since
  that is a common setup. Because each shell reads its own isolated config, this
  indicator is stable and will not flip when another window re-auths.
- A `preexec` hook that warns when an `az` or `aws` command runs while no context
  is selected (env unset), to stop accidental use of the global default store.

## 8. Claude Code integration

Claude Code inherits the shell environment at launch and passes it to every
subprocess, so any `az` or `aws` it runs uses the context's isolated config
automatically. Requirements:

- Only ever start Claude Code from a shell where `ctx use` has run, or via
  `ctx open <name> --claude`.
- Add `ctx claude <name> [project-path]` as a convenience: open a scoped window,
  `cd` to the project, run `claude`.
- This also fixes Terraform and other tools that authenticate through the Azure
  CLI credential, since they shell out to `az` and inherit `AZURE_CONFIG_DIR`.

## 9. Implementation phases

1. Registry and layout. Define `contexts.toml`, create `$HOME/.cloudctx`,
   implement `new` (scaffold only) and `list`.
2. Env core. Implement `cloudctx _env <name>` and the sourced `ctx` shell
   function with `use`, `clear`, `exec`. Prove isolation with two windows before
   adding polish.
3. Auth. Implement `login` and wire it into `new`, for SSO, static keys, and
   assume-role.
4. Visibility. Badge, tab title, tab color, prompt segment, preexec guard.
5. Windowing. `open`, `claude`, dynamic profile generation.
6. Docs. A short README with setup and a migration note (section 11).

## 10. Acceptance tests

- Window 1 `ctx use acme`, window 2 `ctx use globex`. `az account show` in each
  reports a different subscription; `aws sts get-caller-identity` reports a
  different account.
- Run `ctx login globex` in window 2 during a long-running `az` operation in
  window 1. Window 1 keeps its identity throughout.
- Start `claude` in window 1, have it run an `az` command, confirm it targets the
  acme tenant.
- `ctx clear` then run `az account show`, confirm the preexec guard warns.

## 11. Migration and edge cases

- Migration: either move the current `$HOME/.azure` into one context directory to
  preserve an existing login, or just run `ctx new` per customer and re-login.
- GUI-launched terminals do not inherit a scoped env. Always start from a scoped
  shell or via `ctx open`.
- The AWS SSO cache is shared and safe (keyed per session); do not relocate it.
- Token cache file locking is avoided because each context has its own directory.
- Assume the shell is zsh (macOS default) and provide a bash variant of the `ctx`
  function.

## 12. Decisions and open question

Assumed unless told otherwise: zsh primary, full per-context isolation of both
Azure and AWS (not just `AWS_PROFILE`), Python plus Typer for the CLI with a
sourced shell shim, iTerm2 as the only terminal to integrate with.

One thing worth confirming before build, because it changes the `new` and `login`
implementation: are the AWS accounts reached via IAM Identity Center (SSO),
static access keys, or assume-role? The plan supports all three, but knowing the
common case lets Claude Code build that path first.
