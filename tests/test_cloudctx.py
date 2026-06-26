"""Unit tests for the cloudctx CLI.

Run with: python3 -m unittest discover -s tests -v

The CLI lives in an extensionless executable file `cloudctx`, so we load it
as a module via importlib. Every test points the registry at a throwaway temp
dir through $CLOUDCTX_HOME so nothing touches the real ~/.cloudctx.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load():
    # The CLI file has no .py extension, so spec_from_file_location can't infer
    # a loader. Supply a SourceFileLoader explicitly.
    loader = SourceFileLoader("cloudctx", str(ROOT / "cloudctx"))
    spec = importlib.util.spec_from_loader("cloudctx", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cloudctx-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._saved_env = dict(os.environ)
        os.environ["CLOUDCTX_HOME"] = self.tmp
        # isolate the dynamic-profiles target too
        os.environ["CLOUDCTX_PROFILES"] = os.path.join(self.tmp, "profiles.json")
        os.environ.pop("CLOUDCTX_CONTEXT", None)
        self.cc = load()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = self.cc.main(list(args))
        return code, out.getvalue()


class TestList(Base):
    def test_list_empty(self):
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("no contexts", out.lower())


class TestRegistry(Base):
    def test_roundtrip(self):
        data = {"acme": {"display": "Acme AB", "color": "#c0392b",
                         "azure_tenant": "t-1", "azure_subscription": "Prod Sub"}}
        self.cc.save_registry(data)
        self.assertEqual(self.cc.load_registry(), data)

    def test_parse_with_comments(self):
        text = '# top comment\n\n[acme]\ndisplay = "Acme AB"  # trailing comment\ncolor = "#c0392b"\n'
        self.assertEqual(
            self.cc._parse_toml(text),
            {"acme": {"display": "Acme AB", "color": "#c0392b"}},
        )

    def test_missing_file(self):
        self.assertEqual(self.cc.load_registry(), {})

    def test_value_with_special_chars_roundtrips(self):
        # values containing spaces, '#', quotes and backslashes survive
        data = {"x": {"display": 'A "quoted" #1 \\ name'}}
        self.cc.save_registry(data)
        self.assertEqual(self.cc.load_registry(), data)

    def test_hash_inside_quotes_not_treated_as_comment(self):
        text = '[a]\ncolor = "#ff0000"\n'
        self.assertEqual(self.cc._parse_toml(text), {"a": {"color": "#ff0000"}})


class TestNew(Base):
    def test_new_scaffolds_dirs_and_registry(self):
        code, _ = self.run_cli(
            "new", "acme", "--display", "Acme AB", "--color", "#c0392b",
            "--azure-tenant", "t-1", "--azure-subscription", "Prod", "--no-login",
        )
        self.assertEqual(code, 0)
        self.assertTrue(self.cc.azure_dir("acme").is_dir())
        self.assertTrue(self.cc.context_dir("acme").joinpath("aws").is_dir())
        reg = self.cc.load_registry()
        self.assertEqual(reg["acme"]["display"], "Acme AB")
        self.assertEqual(reg["acme"]["azure_tenant"], "t-1")

    def test_new_rejects_duplicate(self):
        self.run_cli("new", "acme", "--no-login")
        code, out = self.run_cli("new", "acme", "--no-login")
        self.assertNotEqual(code, 0)
        self.assertIn("exists", out.lower())

    def test_new_rejects_invalid_name(self):
        code, out = self.run_cli("new", "a b", "--no-login")
        self.assertNotEqual(code, 0)

    def test_list_marks_active(self):
        self.run_cli("new", "acme", "--no-login")
        self.run_cli("new", "globex", "--no-login")
        os.environ["CLOUDCTX_CONTEXT"] = "globex"
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("acme", out)
        self.assertIn("globex", out)
        # the active line is the one marked with *
        active_line = [ln for ln in out.splitlines() if "globex" in ln][0]
        self.assertIn("*", active_line)


class TestEnv(Base):
    def test_azure_only_no_aws_vars(self):
        self.run_cli("new", "acme", "--display", "Acme AB",
                     "--azure-tenant", "t", "--azure-subscription", "Prod", "--no-login")
        code, out = self.run_cli("_env", "acme")
        self.assertEqual(code, 0)
        self.assertIn("export AZURE_CONFIG_DIR=", out)
        self.assertIn("export CLOUDCTX_CONTEXT='acme'", out)
        self.assertIn("export CLOUDCTX_AZURE_LABEL='Prod'", out)
        self.assertNotIn("AWS_PROFILE", out)
        # the azure dir path points inside this context
        self.assertIn(str(self.cc.azure_dir("acme").resolve()), out)

    def test_aws_vars_when_present(self):
        self.run_cli("new", "globex", "--aws-profile", "globex", "--no-login")
        code, out = self.run_cli("_env", "globex")
        self.assertIn("export AWS_PROFILE='globex'", out)
        self.assertIn("export AWS_CONFIG_FILE=", out)
        self.assertIn("export AWS_SHARED_CREDENTIALS_FILE=", out)

    def test_aws_profile_defaults_to_name(self):
        # an aws field present but no explicit aws_profile -> profile defaults to ctx name
        self.run_cli("new", " initech".strip(), "--aws-account-id", "123", "--no-login")
        code, out = self.run_cli("_env", "initech")
        self.assertIn("export AWS_PROFILE='initech'", out)

    def test_injection_safe(self):
        self.run_cli("new", "x", "--azure-subscription", "a'; rm -rf $HOME; '", "--no-login")
        code, out = self.run_cli("_env", "x")
        # the dangerous single quote must be neutralized via the '\'' idiom,
        # so no bare `; rm -rf` escapes the quoting.
        self.assertIn("'\\''", out)
        self.assertNotIn("='a'; rm", out)

    def test_unknown_context_errors_with_empty_stdout(self):
        # stdout must stay empty so `eval "$(... )"` is a safe no-op
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.cc.main(["_env", "nope"])
        self.assertNotEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "")

    def test_clear(self):
        code, out = self.run_cli("_env", "--clear")
        self.assertEqual(code, 0)
        self.assertIn("unset AZURE_CONFIG_DIR", out)
        self.assertIn("unset CLOUDCTX_CONTEXT", out)
        self.assertIn("unset AWS_PROFILE", out)


if __name__ == "__main__":
    unittest.main()
