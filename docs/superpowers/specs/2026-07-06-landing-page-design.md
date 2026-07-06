# cloudctx landing page — static site hosted on Loft

**Status:** approved design
**Date:** 2026-07-06
**Repo:** https://github.com/eliknut/cloudctx
**Hosting:** Loft (https://github.com/larsakerlund/loft), deployed via `loft-cli`

## 1. Objective

A public landing page that pitches cloudctx to someone who has never seen it:
what problem it solves, how it works, how to install and use it. Deployed to the
owner's Loft instance as `https://cloudctx.<loft-domain>` with a single
`loft deploy site cloudctx`.

## 2. Constraints and principles

- **Zero build step.** The `site/` folder in git *is* the deployed artifact.
  Hand-written HTML + CSS only; no node_modules, no bundler, no SSG. This
  mirrors the tool itself (stdlib-only Python, plain zsh/bash shim).
- **No loft-js SDK usage.** Pure static content; the page must work for
  signed-out visitors and needs no identity, DB, or AI features.
- **JavaScript budget: copy-to-clipboard buttons only.** The page must be fully
  functional with JS disabled.
- **Single page.** No routing, no extra pages. GitHub is the docs destination.

## 3. Deliverables

```
site/
├── index.html    all content, semantic sections
├── style.css     terminal-dark theme
└── favicon.svg   simple mark
```

Plus a short "Website" note in the repo README and this spec.

## 4. Page structure

1. **Hero** — project name, pitch ("Per-window cloud CLI context isolation"),
   install one-liner, GitHub button, and a terminal mock of the money shot:
   two side-by-side windows pinned to different customers, both running
   `az account show`, returning different subscriptions.
2. **The problem** — the shared `~/.azure` footgun: the MSAL token cache and
   the active subscription live in one directory every shell shares, so one
   `az login` silently repoints every open window.
3. **How it works** — a context is a credential bundle under
   `~/.cloudctx/<name>`; selecting it exports a fixed set of env vars
   (`AZURE_CONFIG_DIR`, `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`,
   `AWS_PROFILE`). Reproduce the README's env-var table.
4. **Features** — grid of six: the az/aws no-context guard, iTerm2 dynamic
   profiles, Starship prompt segment, `ctx exec`, Claude Code integration,
   AWS-ready registry.
5. **Install + usage** — copy-pasteable snippets styled as terminal windows:
   the clone/symlink/`cloudctx install` block and the `ctx` command tour
   (`new`, `use`, `list`, `status`, `login`, `exec`, `open`, `claude`, `clear`).
6. **Footer** — GitHub link, "hosted on Loft".

Content is sourced from the README; the page must not contradict it.

## 5. Visual direction

Dark terminal aesthetic — the page should feel like the product. Monospace
display type for headings and commands, terminal-chrome code blocks (title bar
with traffic-light dots), one accent color, subtle prompt-glyph motifs.
Responsive down to phones; wide code blocks scroll horizontally inside their
container. Meets WCAG AA contrast on body text.

## 6. Deployment

- One-time: owner runs `loft login <loft-url>` (device flow; cannot be
  automated).
- Deploy: `loft deploy site cloudctx` from the repo root. Redeploys overwrite
  the same site name.
- No CI: the deploy is a manual one-liner by design.

## 7. Verification

- HTML validity (no unclosed tags, valid structure), all links resolve.
- Rendered check in a local browser before deploying (open the file or a
  one-line `python3 -m http.server`).
- Copy buttons degrade gracefully with JS disabled.

## 8. Out of scope

- Multi-page docs, blog, changelog.
- loft-js features (auth, DB, AI chat, realtime).
- Analytics or telemetry of any kind.
- AWS login automation claims — the page must reflect v1 reality (Azure
  proven, AWS registry-ready but login not wired).
