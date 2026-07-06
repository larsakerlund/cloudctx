# CLAUDE.md

Per-window Azure/AWS CLI context isolation: zero-dependency Python 3.9+ CLI
(`cloudctx`, stdlib only) + sourced shell shim (`shell/ctx.zsh`, `shell/ctx.bash`).

## Commands

- `python3 -m unittest discover -s tests -v` — full suite (unit + shell shim + site checks)
- `sh tests/isolation_proof.sh` — two-context isolation acceptance test
- `loft deploy site cloudctx` — deploy landing page → https://cloudctx.loft.redeploy.cloud
  (auth: `loft login https://loft.redeploy.cloud`; device flow prints a code, no browser popup)

## Constraints & gotchas

- No dependencies, ever: CLI is stdlib-only; `site/` is zero-build with no external
  requests (fonts, scripts, CDNs). The folder is the deployed artifact.
- `tests/test_site.py` enforces the site's section ids and an external-link
  allowlist — update `ALLOWED_EXTERNAL` when adding a link.
- Hosted Loft sites sit behind Redeploy Microsoft SSO: anonymous `curl` gets a
  302 to Entra ID; verify pages in a signed-in browser.
- Spec-first workflow: designs in `docs/superpowers/specs/`, plans in
  `docs/superpowers/plans/`.
- Headless Chrome enforces ~500px min window width — for phone-width screenshots,
  render the page inside a 390px iframe harness.
