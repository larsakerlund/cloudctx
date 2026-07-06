# cloudctx Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A zero-build static landing page in `site/`, deployed to the owner's Loft instance as site name `cloudctx` via `loft deploy site cloudctx`.

**Architecture:** Three hand-written files (`index.html`, `style.css`, `favicon.svg`) — no bundler, no node_modules. A stdlib-only unittest validates HTML well-formedness, required sections, and link integrity so the existing `python3 -m unittest discover -s tests` suite covers the site too.

**Tech Stack:** HTML + CSS (system font stacks only), ~20 lines of progressive-enhancement JS for copy buttons, Python stdlib `html.parser` for the checker, `loft-cli` for deployment.

## Global Constraints

- Zero build step: `site/` in git is the deployed artifact, byte for byte.
- No loft-js SDK, no analytics, no external requests (fonts, scripts, images) — the page is fully self-contained.
- JS budget: copy-to-clipboard buttons only; page fully functional with JS disabled (buttons are injected by JS, so no-JS visitors see no dead controls).
- Single page; external links only to `https://github.com/eliknut/cloudctx` and `https://github.com/larsakerlund/loft`.
- Content must not contradict the README — in particular: Azure isolation is proven; AWS registry fields are first-class but `aws sso login` automation is NOT wired yet. Do not claim a license (the repo has no LICENSE file).
- Dark terminal aesthetic; WCAG AA contrast for body text; responsive to phone widths; wide code blocks scroll horizontally inside their own container.
- Python: 3.9+, stdlib only (matches the repo's test suite).

---

### Task 1: Site checker test (failing)

**Files:**
- Test: `tests/test_site.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/test_site.py::SiteTests`, discovered by `python3 -m unittest discover -s tests`. Requires `site/index.html`, `site/style.css`, `site/favicon.svg` to exist; `index.html` must contain section ids `problem`, `how`, `features`, `install`, `usage`, balanced tags, and only allowlisted external links. Task 2 makes it pass.

- [ ] **Step 1: Write the failing test**

Create `tests/test_site.py`:

```python
"""Static checks for the landing page in site/.

Stdlib only. Verifies the three deliverable files exist, the HTML is
well-formed (balanced non-void tags), required section anchors exist,
local href/src targets resolve, and external links stay on the allowlist.
"""
import unittest
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr"}
REQUIRED_IDS = {"problem", "how", "features", "install", "usage"}
ALLOWED_EXTERNAL = {
    "https://github.com/eliknut/cloudctx",
    "https://github.com/larsakerlund/loft",
}


class _Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.ids = set()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append(a[key])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(
                "mismatched </%s> at line %d" % (tag, self.getpos()[0]))
        else:
            self.stack.pop()


def _parse():
    audit = _Audit()
    audit.feed((SITE / "index.html").read_text(encoding="utf-8"))
    return audit


class SiteTests(unittest.TestCase):
    def test_deliverables_exist(self):
        for name in ("index.html", "style.css", "favicon.svg"):
            self.assertTrue((SITE / name).is_file(), "missing site/" + name)

    def test_html_well_formed(self):
        audit = _parse()
        self.assertEqual(audit.errors, [])
        self.assertEqual(audit.stack, [], "unclosed tags: %s" % audit.stack)

    def test_required_sections(self):
        self.assertLessEqual(REQUIRED_IDS, _parse().ids)

    def test_links_resolve(self):
        audit = _parse()
        for ref in audit.refs:
            if ref.startswith(("http://", "https://")):
                self.assertIn(ref, ALLOWED_EXTERNAL)
            elif ref.startswith("#"):
                self.assertIn(ref[1:], audit.ids, "broken anchor " + ref)
            else:
                self.assertTrue((SITE / ref).is_file(),
                                "broken local ref " + ref)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_site -v`
Expected: FAIL — `test_deliverables_exist` fails with `missing site/index.html`; the parse-based tests error with `FileNotFoundError` for `site/index.html`. Both are acceptable failure shapes; the point is nothing passes vacuously.

- [ ] **Step 3: Commit**

```bash
git add tests/test_site.py
git commit -m "test: static checks for the landing page (files, HTML, links)"
```

---

### Task 2: The page — favicon, stylesheet, index.html

**Files:**
- Create: `site/favicon.svg`
- Create: `site/style.css`
- Create: `site/index.html`

**Interfaces:**
- Consumes: `tests/test_site.py` from Task 1 (its REQUIRED_IDS and ALLOWED_EXTERNAL sets are the contract).
- Produces: the deployable `site/` folder Task 4 serves and Task 5 deploys.

**Execution notes:**
- Invoke the `frontend-design` skill before writing the files; the code below is the complete, working baseline — the skill may refine visual polish (spacing, type scale, color tuning) but must keep the structure, copy, ids, and the no-external-requests constraint intact.
- The hero terminal transcript (the two-window demo) is product voice. Offer the user the chance to author it before finalizing; the content below is the default.

- [ ] **Step 1: Create `site/favicon.svg`**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#0b0f14"/>
  <path d="M9 11l6 5-6 5" stroke="#2fbf71" stroke-width="3"
        fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M17 21h7" stroke="#d7dde4" stroke-width="3" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 2: Create `site/style.css`**

```css
/* cloudctx landing page — terminal-dark, no external requests. */
:root {
  --bg: #0b0f14;
  --panel: #11161d;
  --panel-edge: #1d2632;
  --text: #d7dde4;
  --muted: #94a1ae;
  --accent: #2fbf71;
  --acme: #e05b4b;
  --globex: #4b9fe0;
  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3, code, pre, .brand { font-family: var(--mono); }

a { color: var(--accent); }
a:hover { text-decoration: none; }

.wrap { max-width: 68rem; margin: 0 auto; padding: 0 1.25rem; }

/* ---- nav + hero ---- */
nav {
  display: flex; justify-content: space-between; align-items: center;
  padding: 1.25rem 0;
}
.brand { font-weight: 700; letter-spacing: -0.02em; }
.brand::before { content: "❯ "; color: var(--accent); }

.hero { padding: 3rem 0 4rem; }
.hero h1 {
  font-size: clamp(1.7rem, 4.5vw, 2.8rem);
  line-height: 1.2;
  letter-spacing: -0.03em;
  margin: 0 0 1rem;
}
.hero .pitch {
  max-width: 44rem;
  color: var(--muted);
  font-size: 1.1rem;
  margin: 0 0 2rem;
}
.hero .pitch code { color: var(--text); }

.actions { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 3rem; }
.btn {
  display: inline-block;
  padding: 0.6rem 1.1rem;
  border-radius: 6px;
  border: 1px solid var(--panel-edge);
  font-family: var(--mono);
  font-size: 0.9rem;
  text-decoration: none;
  color: var(--text);
}
.btn.primary { background: var(--accent); border-color: var(--accent); color: #06130c; font-weight: 700; }

/* ---- terminal chrome ---- */
.term {
  background: var(--panel);
  border: 1px solid var(--panel-edge);
  border-radius: 10px;
  overflow: hidden;
}
.term-bar {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.55rem 0.9rem;
  border-bottom: 1px solid var(--panel-edge);
  font-family: var(--mono); font-size: 0.75rem; color: var(--muted);
}
.dots { display: inline-flex; gap: 0.35rem; }
.dots i { width: 0.7rem; height: 0.7rem; border-radius: 50%; }
.dots i:nth-child(1) { background: #ff5f56; }
.dots i:nth-child(2) { background: #ffbd2e; }
.dots i:nth-child(3) { background: #27c93f; }

.term pre {
  margin: 0; padding: 1rem;
  overflow-x: auto;
  font-size: 0.85rem; line-height: 1.7;
}
.term .prompt { color: var(--accent); }
.term .out { color: var(--muted); }
.term .warn { color: #ffbd2e; }
.term { position: relative; }
.copy-btn {
  position: absolute; top: 0.4rem; right: 0.5rem;
  background: var(--panel-edge); color: var(--muted);
  border: 0; border-radius: 5px;
  font-family: var(--mono); font-size: 0.7rem;
  padding: 0.25rem 0.6rem; cursor: pointer;
}
.copy-btn:hover { color: var(--text); }

/* ---- hero demo: two windows ---- */
.demo { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.demo .term.acme .term-bar { color: var(--acme); box-shadow: inset 0 2px 0 var(--acme); }
.demo .term.globex .term-bar { color: var(--globex); box-shadow: inset 0 2px 0 var(--globex); }
.demo-caption {
  text-align: center; color: var(--muted);
  font-family: var(--mono); font-size: 0.85rem;
  margin-top: 1rem;
}

/* ---- sections ---- */
section { padding: 3.5rem 0; border-top: 1px solid var(--panel-edge); }
section h2 { font-size: 1.4rem; letter-spacing: -0.02em; margin: 0 0 0.5rem; }
section h2::before { content: "## "; color: var(--accent); }
section > .wrap > p { max-width: 44rem; color: var(--muted); }
section p code, td code { color: var(--text); background: var(--panel); padding: 0.1em 0.35em; border-radius: 4px; }

/* ---- env table ---- */
.env-scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin-top: 1.5rem; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.6rem 0.9rem; border: 1px solid var(--panel-edge); }
th { background: var(--panel); font-family: var(--mono); font-weight: 600; }
td:first-child { font-family: var(--mono); white-space: nowrap; }

/* ---- feature grid ---- */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem; margin-top: 1.5rem;
}
.card {
  background: var(--panel);
  border: 1px solid var(--panel-edge);
  border-radius: 10px;
  padding: 1.1rem 1.2rem;
}
.card h3 { margin: 0 0 0.4rem; font-size: 0.95rem; color: var(--accent); }
.card p { margin: 0; color: var(--muted); font-size: 0.9rem; }

/* ---- footer ---- */
footer {
  border-top: 1px solid var(--panel-edge);
  padding: 2rem 0 3rem;
  color: var(--muted); font-family: var(--mono); font-size: 0.85rem;
}
footer .wrap { display: flex; flex-wrap: wrap; gap: 1rem; justify-content: space-between; }

@media (max-width: 44rem) {
  .demo { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3: Create `site/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>cloudctx — per-window cloud CLI context isolation</title>
<meta name="description" content="cloudctx pins each terminal window to exactly one named cloud identity. Isolated AZURE_CONFIG_DIR per context, so az login in one window never touches another.">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="stylesheet" href="style.css">
</head>
<body>

<header class="hero">
  <div class="wrap">
    <nav>
      <span class="brand">cloudctx</span>
      <a class="btn" href="https://github.com/eliknut/cloudctx">GitHub</a>
    </nav>
    <h1>One machine. Many customers.<br>Zero cross-contamination.</h1>
    <p class="pitch">cloudctx pins each iTerm2 window to exactly one named cloud
    identity, so <code>az login</code> or <code>az account set</code> in one
    window can never silently change the active subscription in another.</p>
    <div class="actions">
      <a class="btn primary" href="#install">Install</a>
      <a class="btn" href="#how">How it works</a>
    </div>
    <div class="demo">
      <div class="term acme">
        <div class="term-bar"><span class="dots"><i></i><i></i><i></i></span>acme — Acme AB</div>
        <pre><span class="prompt">$</span> ctx use acme
<span class="out">✔ context: acme (Acme AB)</span>
<span class="prompt">$</span> az account show --query name
<span class="out">"Acme AB — Production"</span></pre>
      </div>
      <div class="term globex">
        <div class="term-bar"><span class="dots"><i></i><i></i><i></i></span>globex — Globex Corp</div>
        <pre><span class="prompt">$</span> ctx use globex
<span class="out">✔ context: globex (Globex Corp)</span>
<span class="prompt">$</span> az account show --query name
<span class="out">"Globex — Dev"</span></pre>
      </div>
    </div>
    <p class="demo-caption">Two windows. Two tenants. Same machine, at the same time.</p>
  </div>
</header>

<main>
  <section id="problem">
    <div class="wrap">
      <h2>The problem</h2>
      <p>The Azure CLI keeps all of its state — the MSAL token cache <em>and</em>
      the active subscription — inside a single directory,
      <code>AZURE_CONFIG_DIR</code> (default <code>~/.azure</code>). Every shell
      shares it. Log in to a different customer tenant in one window and every
      other window silently repoints. If you work with multiple customers, that
      is an incident waiting to happen.</p>
    </div>
  </section>

  <section id="how">
    <div class="wrap">
      <h2>How it works</h2>
      <p>A <strong>context</strong> is a credential bundle under
      <code>~/.cloudctx/&lt;name&gt;/</code>. Selecting one exports a fixed set
      of environment variables into the current shell — and because the active
      Azure subscription lives <em>inside</em> <code>AZURE_CONFIG_DIR</code>,
      two windows with different exports cannot interfere.</p>
      <div class="env-scroll">
      <table>
        <tr><th>Variable</th><th>Points at</th></tr>
        <tr><td>AZURE_CONFIG_DIR</td><td><code>~/.cloudctx/&lt;name&gt;/azure/</code> — token cache + active subscription</td></tr>
        <tr><td>AWS_CONFIG_FILE</td><td><code>~/.cloudctx/&lt;name&gt;/aws/config</code> <em>(when the context defines AWS fields)</em></td></tr>
        <tr><td>AWS_SHARED_CREDENTIALS_FILE</td><td><code>~/.cloudctx/&lt;name&gt;/aws/credentials</code> <em>(ditto)</em></td></tr>
        <tr><td>AWS_PROFILE</td><td>the context's profile name <em>(ditto)</em></td></tr>
      </table>
      </div>
      <p>A tiny sourced shell function (<code>ctx</code>) does the part a binary
      can't — mutating the parent shell — and everything else is a
      zero-dependency Python CLI.</p>
    </div>
  </section>

  <section id="features">
    <div class="wrap">
      <h2>Features</h2>
      <div class="grid">
        <div class="card"><h3>The guard</h3><p>Run <code>az</code> or <code>aws</code> with no context selected and the shim warns you before you touch the global default store.</p></div>
        <div class="card"><h3>iTerm2 dynamic profiles</h3><p>Every context becomes an iTerm2 profile: pick a customer from the menu, get a correctly scoped, color-coded window.</p></div>
        <div class="card"><h3>Starship segment</h3><p>The active context sits in your prompt, so you always know which identity a window holds.</p></div>
        <div class="card"><h3>ctx exec</h3><p>Run one command in a context — <code>ctx exec acme -- terraform plan</code> — without changing the shell you're in.</p></div>
        <div class="card"><h3>Claude Code ready</h3><p>Agents inherit the shell environment, so any <code>az</code> or Terraform they run stays inside the window's context.</p></div>
        <div class="card"><h3>AWS-ready registry</h3><p>AWS fields are first-class and exported when present. SSO login automation is on the roadmap.</p></div>
      </div>
    </div>
  </section>

  <section id="install">
    <div class="wrap">
      <h2>Install</h2>
      <p>Requires Python 3.9+ (stdlib only) and, for Azure auth, the Azure CLI.</p>
      <div class="term">
        <div class="term-bar"><span class="dots"><i></i><i></i><i></i></span>install</div>
        <pre>git clone https://github.com/eliknut/cloudctx ~/code/cloudctx
ln -s ~/code/cloudctx/cloudctx ~/bin/cloudctx
cloudctx install --write   <span class="out"># hook the ctx shim into your shell rc</span></pre>
      </div>
    </div>
  </section>

  <section id="usage">
    <div class="wrap">
      <h2>Usage</h2>
      <div class="term">
        <div class="term-bar"><span class="dots"><i></i><i></i><i></i></span>usage</div>
        <pre>ctx new acme --display "Acme AB" --color "#c0392b" \
    --azure-tenant &lt;tenant-guid&gt; --azure-subscription "&lt;sub&gt;"
ctx use acme      <span class="out"># scope THIS shell + badge the window</span>
ctx status        <span class="out"># the REAL identity here: az account show</span>
ctx exec acme -- terraform plan
ctx claude acme ~/proj   <span class="out"># scoped iTerm2 window running Claude Code</span>
ctx clear</pre>
      </div>
      <div class="term" style="margin-top:1rem">
        <div class="term-bar"><span class="dots"><i></i><i></i><i></i></span>the guard</div>
        <pre><span class="prompt">$</span> ctx clear
<span class="prompt">$</span> az account show
<span class="warn">cloudctx: WARNING — 'az' run with no context selected. Run 'ctx use &lt;name&gt;' first.</span></pre>
      </div>
    </div>
  </section>
</main>

<footer>
  <div class="wrap">
    <span>cloudctx — <a href="https://github.com/eliknut/cloudctx">github.com/eliknut/cloudctx</a></span>
    <span>hosted on <a href="https://github.com/larsakerlund/loft">Loft</a></span>
  </div>
</footer>

<script>
document.querySelectorAll(".term pre").forEach(function (pre) {
  var btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.textContent = "copy";
  btn.addEventListener("click", function () {
    navigator.clipboard.writeText(pre.textContent).then(function () {
      btn.textContent = "copied";
      setTimeout(function () { btn.textContent = "copy"; }, 1500);
    });
  });
  pre.parentElement.appendChild(btn);
});
</script>

</body>
</html>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_site -v`
Expected: PASS — 4 tests OK.

Then the full suite to prove nothing regressed:
Run: `python3 -m unittest discover -s tests -v`
Expected: PASS (existing cloudctx + shell tests plus the 4 new ones).

- [ ] **Step 5: Commit**

```bash
git add site/
git commit -m "feat: static landing page (terminal-dark, zero-build)"
```

---

### Task 3: README website note

**Files:**
- Modify: `README.md` (after the intro paragraph block, before `## Why`)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing downstream; documentation only.

- [ ] **Step 1: Add the note**

Insert after the v1 status blockquote in `README.md`:

```markdown
**Website:** the landing page lives in [`site/`](site/) and is deployed to a
[Loft](https://github.com/larsakerlund/loft) instance with
`loft deploy site cloudctx` (zero build step — the folder is the artifact).
```

- [ ] **Step 2: Run the full suite (README is untested, but keep the habit)**

Run: `python3 -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: note the Loft-hosted landing page"
```

---

### Task 4: Local render verification

**Files:**
- None created; fixes (if any) land in `site/`.

**Interfaces:**
- Consumes: `site/` from Task 2.
- Produces: a visually verified page for Task 5 to deploy.

- [ ] **Step 1: Serve the folder**

Run: `python3 -m http.server 8123 --directory site` (background)
Expected: `Serving HTTP on :: port 8123`.

- [ ] **Step 2: Render and inspect**

Open/screenshot `http://localhost:8123` in a browser at desktop (~1280px) and
phone (~390px) widths. Check: hero demo side-by-side on desktop and stacked on
phone; no horizontal body scroll at 390px; code blocks scroll internally;
copy button appears on hover and works.

- [ ] **Step 3: Fix and re-verify anything broken, then commit if changed**

```bash
git add site/ && git commit -m "fix: render fixes from local verification"
```

(Skip the commit if nothing changed.)

---

### Task 5: Deploy to Loft

**Files:**
- None.

**Interfaces:**
- Consumes: verified `site/` folder.
- Produces: live site `https://cloudctx.<loft-domain>`.

- [ ] **Step 1: Confirm authentication**

Run: `loft whoami`
Expected: an identity. If it prints `error: not authenticated`, STOP and ask
the owner to run `loft login <their-loft-url>` (device flow — cannot be
automated), then re-run `loft whoami`.

- [ ] **Step 2: Deploy**

Run from the repo root: `loft deploy site cloudctx`
Expected: success output ending with the live URL `https://cloudctx.<loft-domain>`.

- [ ] **Step 3: Verify the live site**

Run: `curl -sI https://cloudctx.<loft-domain> | head -1`
Expected: `HTTP/2 200` (or `HTTP/1.1 200 OK`). Then fetch the body and confirm
it contains `cloudctx — per-window cloud CLI context isolation`.

- [ ] **Step 4: Report**

Report the live URL to the owner. Branch integration (PR vs merge) is the
owner's call — use the superpowers:finishing-a-development-branch skill.
