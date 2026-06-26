"""Tests for the sourced shell shims (shell/ctx.zsh, shell/ctx.bash).

These drive real zsh/bash subprocesses, so they're skipped when the shell
isn't installed. A throwaway $CLOUDCTX_HOME and a stubbed `cloudctx` on PATH
keep them hermetic (no real Azure/iTerm2 needed).
"""
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARK = "CCTX="


def base_env(home):
    env = dict(os.environ)
    env["CLOUDCTX_HOME"] = home
    env["PATH"] = f"{ROOT}:{env.get('PATH', '')}"  # find the real `cloudctx`
    env.pop("CLOUDCTX_CONTEXT", None)
    return env


def extract(output):
    """Pull the `CCTX=...` marker out of output that may be prefixed by raw
    iTerm2 escape bytes emitted by `_decorate`."""
    idx = output.rfind(MARK)
    if idx == -1:
        return None
    return output[idx + len(MARK):].splitlines()[0]


@unittest.skipUnless(shutil.which("zsh"), "zsh not installed")
class TestShimZsh(unittest.TestCase):
    shell = "zsh"
    rcflag = "-f"

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cctx-sh-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.env = base_env(self.home)
        subprocess.run([str(ROOT / "cloudctx"), "new", "acme", "--display",
                        "Acme AB", "--color", "#c0392b", "--azure-tenant", "t",
                        "--azure-subscription", "Prod", "--no-login"],
                       env=self.env, check=True, capture_output=True)

    def run_script(self, body):
        script = f"source {ROOT}/shell/ctx.{self.shell}\n" + textwrap.dedent(body)
        r = subprocess.run([self.shell, self.rcflag, "-c", script],
                           env=self.env, capture_output=True, text=True)
        return r

    def test_use_sets_env(self):
        r = self.run_script(f'''
            ctx use acme >/dev/null
            print -r -- "{MARK}$CLOUDCTX_CONTEXT|$AZURE_CONFIG_DIR"
        ''' if self.shell == "zsh" else f'''
            ctx use acme >/dev/null
            echo "{MARK}$CLOUDCTX_CONTEXT|$AZURE_CONFIG_DIR"
        ''')
        val = extract(r.stdout)
        self.assertIsNotNone(val, msg=r.stderr)
        ctx, _, azdir = val.partition("|")
        self.assertEqual(ctx, "acme")
        self.assertIn(os.path.join("acme", "azure"), azdir)

    def test_clear_unsets_context(self):
        echo = "print -r --" if self.shell == "zsh" else "echo"
        r = self.run_script(f'''
            ctx use acme >/dev/null
            ctx clear >/dev/null
            {echo} "{MARK}[$CLOUDCTX_CONTEXT]"
        ''')
        val = extract(r.stdout)
        self.assertEqual(val, "[]", msg=r.stderr)

    def test_unknown_subcommand_delegates_to_binary(self):
        echo = "print -r --" if self.shell == "zsh" else "echo"
        r = self.run_script(f'''
            ctx list >/tmp/cctx_list_$$ 2>&1
            {echo} "{MARK}$(grep -c acme /tmp/cctx_list_$$)"
            rm -f /tmp/cctx_list_$$
        ''')
        self.assertEqual(extract(r.stdout), "1", msg=r.stderr)

    # --- Task 7: prompt segment + guard ---
    pvar = "PROMPT"

    def test_guard_warns_without_context(self):
        r = self.run_script('_cctx_guard az')
        self.assertIn("no context", r.stderr.lower(), msg=r.stderr)

    def test_guard_silent_with_context(self):
        r = self.run_script('''
            ctx use acme >/dev/null
            _cctx_guard az
        ''')
        self.assertNotIn("no context", r.stderr.lower(), msg=r.stderr)

    def test_guard_ignores_non_cloud_commands(self):
        r = self.run_script('_cctx_guard ls')
        self.assertEqual(r.stderr.strip(), "", msg=r.stderr)

    def test_prompt_has_context_segment(self):
        echo = "print -r --" if self.shell == "zsh" else "echo"
        r = self.run_script(f'{echo} "{MARK}${self.pvar}"')
        self.assertIn("CLOUDCTX_CONTEXT", extract(r.stdout) or "", msg=r.stderr)

    # --- review regression tests ---
    def _new(self, *args):
        subprocess.run([str(ROOT / "cloudctx"), "new", *args, "--no-login"],
                       env=self.env, check=True, capture_output=True)

    def test_switch_clears_stale_aws_vars(self):
        # Findings #2/#3: switching AWS context -> Azure-only must clear AWS_*.
        self._new("awsctx", "--aws-profile", "awsctx")
        echo = "print -r --" if self.shell == "zsh" else "echo"
        r = self.run_script(f'''
            ctx use awsctx >/dev/null
            ctx use acme >/dev/null
            {echo} "{MARK}[$CLOUDCTX_CONTEXT|$AWS_PROFILE|$CLOUDCTX_AZURE_LABEL]"
        ''')
        self.assertEqual(extract(r.stdout), "[acme||Prod]", msg=r.stderr)

    def test_switch_clears_stale_label(self):
        # Finding #7: Azure(sub) -> Azure(no sub) must clear the label.
        self._new("bare", "--azure-tenant", "t2")
        echo = "print -r --" if self.shell == "zsh" else "echo"
        r = self.run_script(f'''
            ctx use acme >/dev/null
            ctx use bare >/dev/null
            {echo} "{MARK}[$CLOUDCTX_CONTEXT|$CLOUDCTX_AZURE_LABEL]"
        ''')
        self.assertEqual(extract(r.stdout), "[bare|]", msg=r.stderr)

    def test_guard_strips_wrappers(self):
        # Finding #15: `sudo az ...` should still trigger the guard.
        r = self.run_script('_cctx_guard "sudo az login"')
        self.assertIn("no context", r.stderr.lower(), msg=r.stderr)

    def test_guard_strips_assignments(self):
        # Finding #15: leading VAR=val assignments should be skipped.
        r = self.run_script('_cctx_guard "FOO=bar aws s3 ls"')
        self.assertIn("no context", r.stderr.lower(), msg=r.stderr)

    def test_zsh_prompt_escapes_percent(self):
        # Finding #14: a '%' in the subscription label must not be a prompt escape.
        # Assert (a) the PROMPT embeds the %-doubling, and (b) that idiom renders
        # a literal % under zsh prompt expansion (${(%)...}). If % were NOT
        # doubled, '100%n' would prompt-expand to '100<username>'.
        if self.shell != "zsh":
            self.skipTest("zsh-specific prompt percent escaping")
        r = self.run_script(r'''
            case "$PROMPT" in
              *'//\%/%%'*) hasesc=yes ;;
              *) hasesc=no ;;
            esac
            label='100%n'
            esc="${label//\%/%%}"
            print -r -- "CCTX=$hasesc|${(%)esc}"
        ''')
        self.assertEqual(extract(r.stdout), "yes|100%n", msg=r.stderr)

    def test_bash_debug_trap_chains(self):
        # Finding #8: sourcing the shim must not clobber a pre-existing DEBUG trap.
        # Check the prior handler still fires for a command issued AFTER sourcing
        # (a marker file, cleared post-source, isolates that from source-time fires).
        if self.shell != "bash":
            self.skipTest("bash-specific DEBUG trap chaining")
        script = (
            'M=$(mktemp)\n'
            "trap 'echo X >> \"$M\"' DEBUG\n"
            f"source {ROOT}/shell/ctx.bash\n"
            ': > "$M"\n'        # clear fires that happened during sourcing
            'true\n'            # post-source command must re-trigger the prior trap
            'n=$(wc -l < "$M"); rm -f "$M"\n'
            'echo "CCTX=$n"\n'
        )
        r = subprocess.run([self.shell, "--norc", "--noprofile", "-c", script],
                           env=self.env, capture_output=True, text=True)
        n = extract(r.stdout)
        self.assertTrue(n and int(n.strip()) > 0,
                        msg=f"prior DEBUG trap was clobbered (n={n}) {r.stderr}")


@unittest.skipUnless(shutil.which("bash"), "bash not installed")
class TestShimBash(TestShimZsh):
    shell = "bash"
    rcflag = "--norc"
    pvar = "PS1"

    def run_script(self, body):
        script = f"source {ROOT}/shell/ctx.{self.shell}\n" + textwrap.dedent(body)
        r = subprocess.run([self.shell, "--norc", "--noprofile", "-c", script],
                           env=self.env, capture_output=True, text=True)
        return r


if __name__ == "__main__":
    unittest.main()
