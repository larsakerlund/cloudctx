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
import stat
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = str(ROOT / "cloudctx")


def write_stub(directory, name, body):
    """Drop an executable shell stub (e.g. a fake `az`) into `directory`."""
    p = Path(directory) / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


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


class TestDecorate(Base):
    def setUp(self):
        super().setUp()
        self.run_cli("new", "acme", "--display", "Acme AB", "--color", "#c0392b",
                     "--azure-tenant", "t", "--no-login")

    def test_badge_is_base64_of_display(self):
        import base64
        code, out = self.run_cli("_decorate", "acme")
        self.assertEqual(code, 0)
        b64 = base64.b64encode("Acme AB".encode()).decode()
        self.assertIn("\x1b]1337;SetBadgeFormat=" + b64 + "\x07", out)

    def test_title_sequence(self):
        _, out = self.run_cli("_decorate", "acme")
        self.assertIn("\x1b]0;Acme AB\x07", out)

    def test_tab_color_is_packed_hex_no_hash(self):
        _, out = self.run_cli("_decorate", "acme")
        self.assertIn("\x1b]1337;SetColors=tab=c0392b\x07", out)

    def test_clear_resets_tab_color(self):
        _, out = self.run_cli("_decorate", "--clear")
        self.assertIn("SetColors=tab=default", out)
        # badge cleared (empty payload)
        self.assertIn("\x1b]1337;SetBadgeFormat=\x07", out)

    def test_hex_to_rgb255(self):
        self.assertEqual(self.cc.hex_to_rgb255("#c0392b"), (192, 57, 43))
        self.assertEqual(self.cc.hex_to_rgb255("c0392b"), (192, 57, 43))
        self.assertEqual(self.cc.hex_to_rgb255("#f00"), (255, 0, 0))

    def test_rgb_floats(self):
        r, g, b = self.cc.rgb_floats("#ff0000")
        self.assertAlmostEqual(r, 1.0)
        self.assertAlmostEqual(g, 0.0)
        self.assertAlmostEqual(b, 0.0)

    def test_no_color_skips_tab_color(self):
        self.run_cli("new", "nocolor", "--display", "No Color", "--no-login")
        _, out = self.run_cli("_decorate", "nocolor")
        self.assertNotIn("SetColors=tab=", out)
        self.assertIn("SetBadgeFormat=", out)  # badge still set


class TestExecStatus(Base):
    def _run_bin(self, *args, extra_path=None):
        env = dict(os.environ)
        env["CLOUDCTX_HOME"] = self.tmp
        if extra_path:
            env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")
        return subprocess.run([CLI, *args], env=env, capture_output=True, text=True)

    def test_exec_sets_context_env(self):
        self.run_cli("new", "acme", "--azure-tenant", "t", "--no-login")
        r = self._run_bin("exec", "acme", "--", "printenv", "AZURE_CONFIG_DIR")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn(os.path.join("acme", "azure"), r.stdout)

    def test_exec_propagates_exit_code(self):
        self.run_cli("new", "acme", "--no-login")
        r = self._run_bin("exec", "acme", "--", "sh", "-c", "exit 7")
        self.assertEqual(r.returncode, 7)

    def test_exec_unknown_context(self):
        r = self._run_bin("exec", "nope", "--", "true")
        self.assertNotEqual(r.returncode, 0)

    def test_status_reports_azure_subscription(self):
        self.run_cli("new", "acme", "--azure-tenant", "t", "--no-login")
        stubdir = tempfile.mkdtemp(prefix="stub-")
        self.addCleanup(shutil.rmtree, stubdir, ignore_errors=True)
        write_stub(stubdir, "az",
                   'echo \'{"name":"Prod Sub","id":"sub-123",'
                   '"tenantId":"t-9","user":{"name":"me@example.com"}}\'')
        r = self._run_bin("status", extra_path=stubdir)
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("Prod Sub", r.stdout)
        self.assertIn("me@example.com", r.stdout)


class TestLogin(Base):
    def test_azure_login_cmds(self):
        entry = {"azure_tenant": "t", "azure_subscription": "s"}
        self.assertEqual(
            self.cc.azure_login_cmds(entry),
            [["az", "login", "--tenant", "t"],
             ["az", "account", "set", "--subscription", "s"]],
        )

    def test_azure_login_cmds_device_code(self):
        entry = {"azure_tenant": "t"}
        cmds = self.cc.azure_login_cmds(entry, device_code=True)
        self.assertEqual(cmds[0], ["az", "login", "--tenant", "t", "--use-device-code"])

    def test_login_dry_run_shows_commands_and_aws_stub(self):
        self.run_cli("new", "acme", "--azure-tenant", "t",
                     "--azure-subscription", "s", "--aws-profile", "acme", "--no-login")
        code, out = self.run_cli("login", "acme", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("az login --tenant t", out)
        self.assertIn("az account set --subscription s", out)
        self.assertIn(str(self.cc.azure_dir("acme").resolve()), out)
        self.assertIn("not yet", out.lower())  # AWS stub

    def test_login_unknown_context(self):
        code, out = self.run_cli("login", "ghost", "--dry-run")
        self.assertNotEqual(code, 0)


class TestOpen(Base):
    def test_applescript_escape(self):
        self.assertEqual(self.cc.applescript_escape('a"b\\c'), 'a\\"b\\\\c')

    def test_open_argv_new_window(self):
        argv = self.cc.open_osascript_argv("ctx use acme", tab=False)
        self.assertEqual(argv[0], "osascript")
        self.assertIn("set _w to (create window with default profile)", argv)
        self.assertIn('write text "ctx use acme"', argv)

    def test_open_argv_new_tab(self):
        argv = self.cc.open_osascript_argv("ctx use acme", tab=True)
        self.assertIn("set _t to (create tab with default profile)", argv)

    def test_build_open_command_cd_and_claude(self):
        cmd = self.cc.build_open_command("acme", cd="/x", claude=True)
        self.assertEqual(cmd, "ctx use acme && cd '/x' && claude")

    def test_open_dry_run(self):
        self.run_cli("new", "acme", "--no-login")
        code, out = self.run_cli("open", "acme", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn('write text "ctx use acme"', out)

    def test_claude_dry_run_includes_claude(self):
        self.run_cli("new", "acme", "--no-login")
        code, out = self.run_cli("claude", "acme", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("&& claude", out)


class TestProfiles(Base):
    def test_build_profiles_shape(self):
        prof = self.cc.build_profiles(
            {"acme": {"display": "Acme AB", "color": "#c0392b"}})
        self.assertEqual(len(prof["Profiles"]), 1)
        p = prof["Profiles"][0]
        self.assertEqual(p["Guid"], "cloudctx-acme")
        self.assertEqual(p["Initial Text"], "ctx use acme")
        self.assertTrue(p["Use Tab Color"])
        self.assertAlmostEqual(p["Tab Color"]["Red Component"], 192 / 255)
        self.assertEqual(p["Tab Color"]["Color Space"], "sRGB")

    def test_no_color_omits_tab_color(self):
        p = self.cc.build_profiles({"x": {"display": "X"}})["Profiles"][0]
        self.assertNotIn("Use Tab Color", p)

    def test_gen_profiles_writes_valid_json(self):
        import json
        self.run_cli("new", "acme", "--color", "#c0392b", "--no-login", "--no-profiles")
        code, _ = self.run_cli("gen-profiles")
        self.assertEqual(code, 0)
        path = self.cc.profiles_path()
        data = json.loads(Path(path).read_text())
        self.assertEqual(data["Profiles"][0]["Guid"], "cloudctx-acme")

    def test_new_regenerates_profiles(self):
        import json
        self.run_cli("new", "acme", "--color", "#2980b9", "--no-login")
        data = json.loads(Path(self.cc.profiles_path()).read_text())
        self.assertEqual(len(data["Profiles"]), 1)


if __name__ == "__main__":
    unittest.main()
