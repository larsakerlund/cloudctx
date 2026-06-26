# cloudctx — per-window Azure / AWS CLI context isolation

**Status:** approved design (v1)
**Date:** 2026-06-26
**Repo:** https://github.com/eliknut/cloudctx (private)

## 1. Objective

Let one machine hold many live cloud identities concurrently. Each iTerm2 window
(and any Claude Code session launched inside it) is pinned to exactly one named
context. Authenticating or switching subscription in one window must have zero
effect on any other window.

The single property that everything else serves: **no window ever silently swaps
context because another window logged in to a different customer tenant.**

## 2. Root cause being designed around

- **Azure CLI** stores active state in one directory, `$AZURE_CONFIG_DIR`
  (default `$HOME/.azure`). `azureProfile.json` records every known subscription
  plus a single `isDefault: true` flag; `msal_token_cache.json` holds tokens. All
  windows share this directory, so `az login` or `az account set` in one window
  flips the active subscription for every window. (Verified on this machine: the
  live `~/.azure/azureProfile.json` is ~108 KB — many subscriptions in one shared
  mutable file.)
- **AWS CLI** has no active-profile file. Resolution order is `--profile`, then
  `AWS_PROFILE`, then the `default` profile. The SSO token cache under
  `$HOME/.aws/sso/cache` is keyed per session, so multiple SSO logins coexist.
  AWS only bleeds when something writes the `default` profile or relies on it.

The fix for both: point each shell at its own credential files through environment
variables, set before any `az` or `aws` command runs.

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
interfere. Re-login in one is invisible to the other. **This is the property the
acceptance tests verify.**

The AWS SSO cache stays at `$HOME/.aws/sso/cache` and is shared across contexts.
That is safe because entries are keyed by the SSO session start URL, so different
customers do not collide. We do not relocate it; AWS has no supported env var for
that path.

## 4. v1 scope decision — Azure-only isolation, AWS-ready schema

(Decided 2026-06-26. AWS CLI is not installed on the build machine, and the common
AWS access pattern was deferred.)

- **Built and proven in v1:** the full isolation property via Azure
  `AZURE_CONFIG_DIR` redirection plus AWS env-var selection.
- **Schema is AWS-ready:** all AWS fields exist in `contexts.toml` and are
  optional. The env core exports the four AWS variables above **whenever a context
  defines AWS fields**, so an AWS context becomes functional the moment the AWS CLI
  is installed and a login has populated the per-context files.
- **Deferred to a later version:** the `aws sso login` / static-key / assume-role
  *automation* inside `ctx new` and `ctx login`. The on-disk layout and env exports
  for AWS are present now so nothing has to be re-architected later.

A context may be Azure-only, AWS-only, or both. v1 exercises Azure-only and
both-fields-present (export path), and leaves AWS auth automation as a stub that
emits clear "not yet implemented; AWS CLI required" guidance.

## 5. Packaging decision — zero-dependency single-file Python CLI

(Decided 2026-06-26. The plan suggested Typer to match an existing AKS stack, but
that stack is not present in this repo, system Python is 3.9, and no package
manager — pipx/uv/poetry — is installed. `ctx use` invokes the CLI on every shell
startup and every context switch, so cold-start latency and zero-install matter.)

- One executable `cloudctx` Python script using **argparse** only. No venv, no
  third-party dependencies. Installs by copying one file onto `PATH`.

### The TOML-on-Python-3.9 wrinkle

`tomllib` only exists in Python 3.11+, and even there it is **read-only** (there is
no stdlib TOML *writer* in any Python version). Resolution:

- **Reading:** use `tomllib` when importable (3.11+); otherwise fall back to a
  small purpose-built parser. The parser handles only our restricted schema — flat
  `[name]` tables, `key = "value"` string pairs, `#` comments, blank lines — which
  is entirely under our control, so it is safe and ~30 lines.
- **Writing:** always hand-rolled (no stdlib option exists regardless of version).
  Values are emitted as quoted TOML strings.

This keeps the `contexts.toml` filename honest while preserving the zero-dependency
promise on the actual build Python (3.9.6).

## 6. On-disk layout

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
display            = "Acme AB"
color              = "#c0392b"               # iTerm2 tab/badge color
azure_tenant       = "<tenant-guid>"
azure_subscription = "<sub-guid-or-name>"    # selected after login
aws_sso_start_url  = "https://acme.awsapps.com/start"   # all aws_* optional in v1
aws_sso_region     = "eu-north-1"
aws_account_id     = "<account-id>"
aws_role           = "<permission-set>"
aws_profile        = "acme"                  # value exported as AWS_PROFILE
```

All `aws_*` fields are optional. `azure_*` fields are optional too (an AWS-only
context is allowed). At least one cloud must be configured for a context to be
useful, but scaffolding does not hard-require either.

The repo itself:

```
cloudctx/
  cloudctx                     # the Python CLI (executable, zero-dep)
  shell/ctx.zsh                # sourced zsh shim + prompt segment + preexec guard
  shell/ctx.bash               # bash variant of the shim
  starship/cloudctx.toml       # Starship custom-segment snippet
  README.md                    # setup + migration note (plan section 11)
  docs/superpowers/specs/2026-06-26-cloudctx-design.md
```

## 7. Architecture — three cooperating units

### 7.1 `cloudctx` (Python CLI)

Owns all logic that does not need to mutate the parent shell: registry read/write,
directory scaffolding, Azure login, status, exec, dynamic-profile generation.

Two **internal** subcommands feed the shell shim and define the contract between
Python and the shell:

- `cloudctx _env <name>` — prints **only** shell statements (`export VAR=value`,
  `unset VAR`). Output is captured and `eval`'d by the shim. Values are
  single-quote-escaped to be injection-safe. Also sets a marker var
  `CLOUDCTX_CONTEXT=<name>` (and a short Azure subscription label + `AWS_PROFILE`
  echo for the prompt). `cloudctx _env --clear` prints the `unset` lines.
- `cloudctx _decorate <name>` — prints **only** the iTerm2 escape sequences
  (badge, tab title, tab color). Run by the shim **without** command substitution
  so the bytes go straight to the controlling tty and render.
  `cloudctx _decorate --clear` resets badge/title/color.

This split keeps env logic in exactly one place (Python) while still letting the
parent shell change, and keeps terminal-control bytes out of the `eval` path.

User-facing subcommands:

| command | mutates parent shell? | behaviour |
|---|---|---|
| `list` | no | list contexts; mark the one active in this shell (`$CLOUDCTX_CONTEXT`) |
| `new <name>` | no | scaffold dir + registry entry (interactive prompts), then guided Azure login |
| `use <name>` | **yes (via shim)** | export env + decorate window |
| `clear` | **yes (via shim)** | unset exported vars + reset decoration |
| `login <name>` | no | (re)authenticate the context into its isolated store |
| `status` / `whoami` | no | `az account show` + `aws sts get-caller-identity` for current shell |
| `open <name> [--cd PATH] [--claude]` | no | launch a new iTerm2 window/tab already scoped |
| `exec <name> -- <cmd...>` | no | run one command with the context env set for that invocation only |
| `claude <name> [path]` | no | convenience: scoped window, cd, run `claude` |

### 7.2 `ctx` shell shim (`shell/ctx.zsh`, `shell/ctx.bash`)

~15-line sourced function. `use`/`clear` do `eval "$(command cloudctx _env …)"`
then `command cloudctx _decorate …`; every other subcommand delegates straight to
the binary. The shim also installs:

- a **prompt segment** showing `CLOUDCTX_CONTEXT` + short Azure subscription label
  + `AWS_PROFILE`, and
- a **preexec guard** (zsh `add-zsh-hook preexec`, bash `DEBUG`-trap equivalent)
  that warns when an `az`/`aws` command runs while no context is selected, to stop
  accidental use of the global default store.

### 7.3 Generated artifacts

`~/.cloudctx/` (registry + per-context stores) and the iTerm2
`~/Library/Application Support/iTerm2/DynamicProfiles/cloudctx.json`, regenerated
on every registry change so the iTerm2 profile menu always matches the registry.

## 8. iTerm2 integration

The exact escape sequences and the dynamic-profile JSON schema will be confirmed
against authoritative iTerm2 documentation during implementation (not hardcoded
from memory) and verified to render before shipping:

- **Badge:** iTerm2 `SetBadgeFormat` OSC sequence, base64 of the display name.
- **Tab title:** title OSC sequence.
- **Tab color:** per-context color OSC sequence.
- **`open`:** iTerm2 Python API or AppleScript to open a new session, then inject
  `ctx use <name>` (and optionally `cd` + `claude`).
- **Dynamic profiles:** one profile per context, each carrying the context color
  and an initial command that runs `ctx use <name>`.

## 9. Claude Code integration

Claude Code inherits the shell environment at launch and passes it to every
subprocess, so any `az`/`aws`/Terraform it runs uses the context's isolated config
automatically. Requirements:

- Only start Claude Code from a shell where `ctx use` has run, or via
  `ctx open <name> --claude` / `ctx claude <name> [path]`.
- This also fixes Terraform and other tools that authenticate through the Azure CLI
  credential, since they shell out to `az` and inherit `AZURE_CONFIG_DIR`.

## 10. Implementation phases

1. **Registry & layout** — `contexts.toml` read/write (with the 3.9 TOML strategy),
   `$HOME/.cloudctx` scaffolding, `new` (scaffold only), `list`.
2. **Env core** — `_env`, `_decorate` (byte output), the sourced `ctx` shim with
   `use`/`clear`/`exec`. Prove two-shell isolation before any polish.
3. **Auth** — `login` and wire into `new` for **Azure** (`az login --tenant …`
   then `az account set --subscription …`). AWS auth left as a guided stub.
4. **Visibility** — badge, tab title, tab color, prompt segment, preexec guard.
5. **Windowing** — `open`, `claude`, dynamic-profile generation.
6. **Docs** — README with setup + migration note.

## 11. Acceptance tests

- Window 1 `ctx use acme`, window 2 `ctx use globex`. `az account show` in each
  reports a different subscription. (AWS `sts get-caller-identity` parity deferred
  with AWS auth.)
- Run `ctx login globex` in window 2 during a long `az` operation in window 1.
  Window 1 keeps its identity throughout.
- Start `claude` in window 1, have it run an `az` command, confirm it targets the
  acme tenant.
- `ctx clear`, then run `az` — confirm the preexec guard warns.

### Verification boundary on the build machine

Fully testable here: registry/scaffold/list, `_env` output correctness, `clear`,
`exec`, `_decorate` byte output, dynamic-profile generation, and a **real
two-shell Azure isolation proof** (the live `~/.azure` makes this exercisable).
Not testable here: any AWS path (CLI absent), and literally opening a second iTerm2
*window* (no GUI driver) — though escape sequences and the open command are
verified to be well-formed.

## 12. Migration and edge cases

- **Migration:** either move the current `$HOME/.azure` into one context directory
  to preserve the existing login, or run `ctx new` per customer and re-login. The
  README documents both; the tool does not auto-migrate (non-destructive default).
- **GUI-launched terminals** do not inherit a scoped env. Always start from a
  scoped shell or via `ctx open`.
- The AWS SSO cache is shared and safe (keyed per session); do not relocate it.
- Token-cache file locking is avoided because each context has its own directory.
- Shell is zsh (macOS default); a bash variant of the `ctx` function ships too.
- **Name collision:** `ctx` is a short name; the shim uses `command cloudctx` to
  avoid recursing and documents how to rename the function if it clashes.
- **Injection safety:** `_env` single-quote-escapes all values so a malicious or
  malformed registry value cannot execute code through the `eval`.

## 13. Open items deferred (not in v1)

- AWS login automation (SSO / static keys / assume-role).
- `aws sts get-caller-identity` half of `status` is implemented but only meaningful
  once AWS is configured.
