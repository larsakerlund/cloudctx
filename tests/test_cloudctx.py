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


if __name__ == "__main__":
    unittest.main()
