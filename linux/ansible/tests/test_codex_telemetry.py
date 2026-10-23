"""Exercise telemetry adoption, credential handling and non-destructive updates."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "roles/codex/files/configure-telemetry.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("codex_telemetry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Telemetry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.toml"
        self.token = self.root / "token"
        self.token.write_text("private-ingest-token\n")

    def configure(self, **kwargs):
        return MODULE.configure(self.config, [self.token],
                                "https://otel.example/v1/metrics", "desktop-wsl", **kwargs)

    def test_preserves_settings_and_is_idempotent(self):
        original = '# personal settings\nmodel_reasoning_effort = "xhigh"\n[features]\nhooks = true\n'
        self.config.write_text(original)
        self.assertEqual(self.configure(), (True, ""))
        text = self.config.read_text()
        self.assertTrue(text.startswith(original))
        config = tomllib.loads(text)
        self.assertEqual(config["model_reasoning_effort"], "xhigh")
        self.assertEqual(config["otel"]["environment"], "desktop-wsl")
        exporter = config["otel"]["metrics_exporter"]["otlp-http"]
        self.assertEqual(exporter["headers"], {"Authorization": "Bearer private-ingest-token"})
        self.assertEqual(exporter["protocol"], "binary")
        self.assertEqual(config["otel"]["exporter"], "none")
        self.assertEqual(config["otel"]["trace_exporter"], "none")
        self.assertFalse(config["otel"]["log_user_prompt"])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.configure(), (False, ""))
        self.assertEqual(self.config.read_text(), text)

    def test_token_rotation_and_removal(self):
        original = 'model = "gpt-6-astra"\n'
        self.config.write_text(original)
        self.configure()
        self.token.write_text("rotated-token")
        self.assertTrue(self.configure()[0])
        self.assertNotIn("private-ingest-token", self.config.read_text())
        self.token.unlink()
        self.assertEqual(self.configure(), (True, "no ingest token"))
        self.assertEqual(self.config.read_text(), original)

    def test_preserves_foreign_tables_interleaved_before_end(self):
        original = 'model = "gpt-6.1-sol"\n'
        foreign = '''# App-owned values, including a multiline string and quoted key.
[desktop]
preventSleepWhileRunning = true
theme = """Dark
[not.a.table]
"""
[desktop.colors]
accent = "#ff79c6"
[plugins."browser@openai-bundled"]
enabled = true
[marketplaces.local]
path = "/private/cache"
[mcp_servers.node_repl.env]
APP_RUNTIME = "/generated/version/path"
'''
        self.config.write_text(original)
        self.configure()
        self.config.write_text(self.config.read_text().replace(MODULE.END, foreign + MODULE.END))
        expected = tomllib.loads(original + foreign)
        before = self.config.read_bytes()
        self.assertTrue(self.configure(check=True)[0])
        self.assertEqual(self.config.read_bytes(), before)
        self.assertTrue(self.configure()[0])
        actual = tomllib.loads(self.config.read_text())
        del actual['otel']
        self.assertEqual(actual, expected)
        self.assertIn('# App-owned values', self.config.read_text())
        self.assertEqual(self.configure(), (False, ''))
        self.token.write_text('rotated-token')
        self.assertTrue(self.configure()[0])
        self.token.unlink()
        self.assertEqual(self.configure(), (True, 'no ingest token'))
        self.assertEqual(tomllib.loads(self.config.read_text()), expected)

    def test_does_not_erase_unowned_otel_settings(self):
        self.configure()
        self.config.write_text(self.config.read_text().replace('[otel]\n', '[otel]\ncustom = "preserve"\n'))
        self.assertEqual(self.configure(), (True, 'existing telemetry configuration'))
        self.assertEqual(tomllib.loads(self.config.read_text()), {'otel': {'custom': 'preserve'}})

    def test_no_token_does_not_create_config(self):
        self.token.unlink()
        self.assertEqual(self.configure(), (False, "no ingest token"))
        self.assertFalse(self.config.exists())

    def test_respects_foreign_telemetry_and_opt_out(self):
        for text, reason in (
            ('[otel]\nexporter = "none"\n', "existing telemetry configuration"),
            ('[profiles.work.otel]\nenvironment = "work"\n', "existing telemetry configuration"),
            ('[analytics]\nenabled = false\n', "analytics disabled"),
        ):
            with self.subTest(text=text):
                self.config.write_text(text)
                self.assertEqual(self.configure(), (False, reason))
                self.assertEqual(self.config.read_text(), text)

    def test_analytics_opt_out_removes_managed_exporter(self):
        self.configure()
        self.config.write_text('[analytics]\nenabled = false\n' + self.config.read_text())
        self.assertEqual(self.configure(), (True, "analytics disabled"))
        self.assertNotIn("otel", tomllib.loads(self.config.read_text()))

    def test_check_mode_never_writes(self):
        self.assertEqual(self.configure(check=True), (True, ""))
        self.assertFalse(self.config.exists())
        self.configure()
        before = self.config.read_bytes()
        self.token.write_text("new-token")
        self.assertEqual(self.configure(check=True), (True, ""))
        self.assertEqual(self.config.read_bytes(), before)

    def test_fallback_token_precedence(self):
        fallback = self.root / "claude-token"
        fallback.write_text("fallback-token")
        args = (self.config, [self.token, fallback], "https://otel.example/v1/metrics", "host")
        MODULE.configure(*args)
        self.assertNotIn("fallback-token", self.config.read_text())
        self.token.unlink()
        MODULE.configure(*args)
        self.assertIn("fallback-token", self.config.read_text())

    def test_fails_without_overwriting_invalid_config(self):
        for text in ('[broken', MODULE.BEGIN + '\n', MODULE.END + '\n'):
            self.config.write_text(text)
            with self.assertRaises(ValueError):
                self.configure()
            self.assertEqual(self.config.read_text(), text)

    def test_refuses_symlink(self):
        target = self.root / "target"
        target.write_text('model = "gpt-6-astra"\n')
        self.config.symlink_to(target)
        with self.assertRaises(ValueError):
            self.configure()
        self.assertNotIn("otel", target.read_text())

    def test_repairs_config_permissions(self):
        self.configure()
        self.config.chmod(0o644)
        self.assertTrue(self.configure()[0])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_escapes_toml_values(self):
        self.token.write_text('token"with\\quotes')
        self.configure()
        headers = tomllib.loads(self.config.read_text())["otel"]["metrics_exporter"]["otlp-http"]["headers"]
        self.assertEqual(headers["Authorization"], 'Bearer token"with\\quotes')

    def test_cli_does_not_print_secrets_on_success_or_failure(self):
        args = [sys.executable, str(SCRIPT), "--config", str(self.config),
                "--token", str(self.token), "--endpoint", "https://otel.example/v1/metrics",
                "--machine", "host"]
        result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=True)
        self.assertEqual(result.stdout, "updated\n")
        self.config.write_text('secret = "private-ingest-token\n')
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("private-ingest-token", result.stderr + result.stdout)

    def test_rejects_invalid_token_and_insecure_endpoint(self):
        for token in ("", "token\nsecond-line", "token\tvalue"):
            self.token.write_text(token)
            with self.assertRaises(ValueError):
                self.configure()
            self.assertFalse(self.config.exists())
        self.token.write_text("valid-token")
        with self.assertRaises(ValueError):
            MODULE.configure(self.config, [self.token], "http://otel.example/v1/metrics", "host")


if __name__ == "__main__":
    unittest.main()
