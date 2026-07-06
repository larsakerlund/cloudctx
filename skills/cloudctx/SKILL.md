---
name: cloudctx
description: Routes all Azure CLI work through the cloudctx tool so each customer's credentials stay isolated per context. Use whenever about to run an `az` command or act on Azure resources via CLI — az login, account/subscription selection, resource groups, VMs, AKS, app services, storage, deployments, ARM/Bicep, key vault, networking, or any `az ...` invocation. Every cloud command must run as `cloudctx exec <context> -- az ...`; never bare `az`, never `ctx use`/export then a separate `az` call. Also covers the `aws` CLI on cloudctx contexts. Do NOT use for purely conceptual or architecture Azure questions that need no CLI (e.g. "what is AKS", "App Service vs Functions", "explain managed identities").
---

# cloudctx — isolated Azure CLI per customer context

You are stateless: each shell command runs in a fresh process, so env vars set by one
command do NOT survive to the next. Azure CLI keeps its token cache AND active
subscription in a single `AZURE_CONFIG_DIR` (default `~/.azure`) shared by every shell,
so bare `az` pollutes one global store and can silently point at the WRONG customer's
subscription. The shell guard that warns on bare `az` does NOT fire for you (it needs a
sourced interactive shell), so routing every command through `cloudctx exec` is your
only protection.

A **context = one customer tenant** with its own isolated `AZURE_CONFIG_DIR`. A tenant
usually holds many subscriptions; you pick the specific one per task (see "Selecting the
subscription").

## The one rule

`cloudctx exec` is the only correct mechanism: it injects the context's isolated env and
runs the command in ONE process, so nothing needs to persist. Run EVERY cloud command as:

```sh
cloudctx exec <context> -- az <args...>
```

```sh
cloudctx exec acme -- az account show -o json
cloudctx exec acme -- az group list -o table
cloudctx exec acme -- az aks get-credentials -g rg-prod -n aks-prod
cloudctx exec acme -- az login --device-code        # scoped, headless login
cloudctx exec acme -- aws s3 ls                      # AWS too, if the context defines aws fields
```

`--` is the separator — always include it. Any command works after it, not just `az`
(e.g. `cloudctx exec acme -- terraform plan`).

## Contexts currently on this machine

!`cloudctx list`

Empty output (`no contexts...`) means none exist yet — see "When no context exists".

## Choosing the context

1. Run `cloudctx list` (its output is shown above when available) and pick the context
   matching the customer/tenant you were asked to act on.
2. If the match is ambiguous, ASK the user — do not guess.
3. Verify identity before anything destructive:
   `cloudctx exec <context> -- cloudctx status` (prints account name/id/tenant/user).

## When no context exists

If `cloudctx list` shows `no contexts...` or none matches, STOP — do NOT fall back to
bare `az`. Ask the user, then offer to create one:

```sh
cloudctx new <name> --display "Human Label" --azure-tenant <tenant-guid>
```

- Tenant only — do NOT pass `--azure-subscription`; the sub is chosen per task, and
  pinning one goes stale (sub ids churn). Add it only if the user wants a fixed default.
- Name must match `[A-Za-z0-9_-]+`. The tenant GUID comes from the user.
- `new` runs `az login` interactively (browser); add `--device-code` for headless.
- `--no-login` scaffolds without auth; log in later with `cloudctx login <name> --device-code`.
- `cloudctx login <name> --dry-run` previews the auth commands without running them.

## Selecting the subscription within a context

A context does NOT pin a subscription — the active one is just whatever it last selected,
possibly wrong for the task. Before subscription-specific work:

```sh
cloudctx exec <ctx> -- az account show -o table                      # active sub
cloudctx exec <ctx> -- az account list -o table                      # all subs in this context
cloudctx exec <ctx> -- az account set --subscription "<name-or-id>"  # switch (persists)
```

Or scope one command without changing the active sub:

```sh
cloudctx exec <ctx> -- az group list --subscription "<name-or-id>" -o table
```

If the user names an environment (prod/test/qa) or subscription and the match is
ambiguous, confirm WHICH before acting — never guess on a destructive op.

## Never

- ❌ bare `az ...` — hits the global store (see above).
- ❌ `ctx use <ctx>` then a separate `az ...` — the env dies with that shell, so the next
  `az` has no `AZURE_CONFIG_DIR` (and `ctx use` needs a sourced shim a fresh shell may lack).
- ❌ `export AZURE_CONFIG_DIR=...` then `az ...` in a later command — same reason.
