"""Tests for tools/autonomous/config_scan.py, the DAL-281 snapshot gate.

Two failure modes matter here and they pull in opposite directions.

Miss a real credential and the weekly job publishes it to a public repo. Block
on prose or on a path reference and the gate cries wolf, someone switches it
off, and we are back to no gate at all. So the fixtures below are lifted from
the files this actually runs against: the live Caddyfile's comment about a
token, gandon-hook.service's EnvironmentFile line, and the Plausible compose
file both before and after DAL-281 moved POSTGRES_PASSWORD out of it.
"""

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "tools" / "autonomous" / "config_scan.py"
_spec = importlib.util.spec_from_file_location("config_scan", MODULE_PATH)
config_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_scan)


class BlocksRealSecrets(unittest.TestCase):
    def assertBlocked(self, text, msg=None):
        self.assertTrue(config_scan.scan_text(text), msg or f"should have blocked: {text!r}")

    def test_inline_password_is_blocked(self):
        # The exact shape DAL-281 found at docker-compose.yml line 13.
        self.assertBlocked("      - POSTGRES_PASSWORD=s3cr3tvalue")

    def test_yaml_colon_form_is_blocked(self):
        self.assertBlocked("  POSTGRES_PASSWORD: s3cr3tvalue")

    def test_quoted_value_is_blocked(self):
        self.assertBlocked('SECRET_KEY_BASE="abcdef123456"')

    def test_commented_out_secret_is_still_blocked(self):
        # A published credential is published whether or not it is commented.
        self.assertBlocked("# POSTGRES_PASSWORD=s3cr3tvalue")

    def test_private_key_block_is_blocked(self):
        self.assertBlocked("-----BEGIN RSA PRIVATE KEY-----")
        self.assertBlocked("-----BEGIN PRIVATE KEY-----")

    def test_aws_access_key_is_blocked(self):
        self.assertBlocked("aws_access_key_id = AKIAIOSFODNN7EXAMPLE")

    def test_literal_bearer_token_is_blocked(self):
        self.assertBlocked("header Authorization Bearer sk_live_abcdef0123456789xyz")

    def test_vendor_tokens_are_blocked_wherever_they_appear(self):
        """Tokens that identify themselves need no surrounding context.

        The 2026-08-20 incident was a Shopify token sitting in a DEFAULT
        ARGUMENT, which is not an assignment value, so the name-and-literal
        heuristic reached it only by accident of line shape. These do not
        depend on that.
        """
        shpat = "shpat_" + "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
        self.assertBlocked('TOKEN = os.environ.get("SHOPIFY_ADMIN_API", "%s")' % shpat)
        self.assertBlocked('headers = {"X-Shopify-Access-Token": "%s"}' % shpat)
        self.assertBlocked("curl -H 'X-Token: %s' https://example.com" % shpat)
        self.assertBlocked("ghp_" + "0123456789abcdef0123456789abcdef0123")
        self.assertBlocked("xoxb-" + "12345678901-abcdefghijkl")

    def test_source_style_does_not_cry_wolf_at_a_reference(self):
        """The correct way to write it must not be blocked.

        `TOKEN = os.environ.get(...)` is a reference, not a credential. In a
        config file a bare value IS the credential, so the two styles differ.
        """
        line = 'TOKEN = os.environ.get("SHOPIFY_ADMIN_API")'
        self.assertEqual(config_scan.scan_text(line, style="source"), [])
        # Same line judged as config still blocks: a Caddyfile value is literal.
        self.assertTrue(config_scan.scan_text(line, style="config"))

    def test_source_style_still_catches_a_real_credential(self):
        shpat = "shpat_" + "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
        self.assertTrue(config_scan.scan_text('T = "%s"' % shpat, style="source"))
        self.assertTrue(config_scan.scan_text("-----BEGIN PRIVATE KEY-----", style="source"))
        self.assertTrue(config_scan.scan_text("aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
                                     style="source"))

    def test_config_remains_the_default_style(self):
        # The snapshot gate calls scan_text with no style and must not weaken.
        self.assertTrue(config_scan.scan_text("POSTGRES_PASSWORD=hunter2"))

    def test_value_with_a_hash_is_not_truncated_into_looking_safe(self):
        # Naive "strip everything after #" would leave an empty value here and
        # wave a real password through.
        self.assertBlocked('DB_PASSWORD="pa#ssword"')

    def test_reports_every_offending_line(self):
        findings = config_scan.scan_text("A_TOKEN=one\nfine=ok\nB_SECRET=two\n")
        self.assertEqual(len(findings), 2)
        self.assertEqual([f.line_no for f in findings], [1, 3])


class AllowsThingsWeLegitimatelyTrack(unittest.TestCase):
    def assertClean(self, text):
        findings = config_scan.scan_text(text)
        self.assertEqual(findings, [], f"false positive: {[f.describe() for f in findings]}")

    def test_a_word_that_merely_starts_like_a_token_is_not_blocked(self):
        # re_ and sk_ are short. Without a length floor they would fire on
        # ordinary code and the gate would be switched off within a month.
        self.assertClean("re_match = re.compile(r'x')")
        self.assertClean("sk_live_url = build_url()")
        self.assertClean("ghp_count = 3")

    def test_variable_reference_is_clean(self):
        self.assertClean("      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}")
        self.assertClean("      - SECRET_KEY_BASE=${SECRET_KEY_BASE}")
        self.assertClean("PASSWORD=$DB_PASS")
        self.assertClean("TOKEN=$(cat /opt/dale/secrets/tok)")

    def test_environment_file_path_is_clean(self):
        # Straight out of gandon-hook.service line 14.
        self.assertClean("EnvironmentFile=/opt/dale/secrets/lodgify.env")

    def test_prose_about_a_token_is_clean(self):
        # Straight out of the live Caddyfile's gandon block.
        self.assertClean(
            "\t# The token is in the request path, so the URI must not reach the access\n"
            "\t# log. Filter it out rather than turning logging off.\n"
        )

    def test_placeholder_is_clean(self):
        self.assertClean("CF_ACCESS_AUD=<the AUD tag copied above>")
        self.assertClean("API_KEY=REDACTED")

    def test_empty_value_is_clean(self):
        self.assertClean("MAXMIND_LICENSE_KEY=")

    def test_non_sensitive_names_are_clean(self):
        self.assertClean("BASE_URL=https://data.bjnoel.com")
        self.assertClean("CLICKHOUSE_SKIP_USER_SETUP=true")

    def test_referenced_bearer_is_clean(self):
        self.assertClean("header Authorization Bearer ${LODGIFY_TOKEN}")

    def test_real_crontab_sample_is_clean(self):
        self.assertClean(
            "0 * * * * /opt/dale/autonomous/dale-runner.sh >> /opt/dale/autonomous/logs/cron.log 2>&1\n"
            "0 3 * * 1 /usr/bin/python3 /opt/dale/autonomous/linear_update.py archive-stale --days 30 --execute\n"
            "*/5 * * * * /usr/bin/python3 /opt/dale/autonomous/uptime_monitor.py\n"
        )

    def test_real_systemd_unit_is_clean(self):
        self.assertClean(
            "[Service]\n"
            "User=dale\n"
            "ExecStart=/usr/bin/python3 /opt/dale/scrapers/subscribe_server.py\n"
            "Restart=always\n"
            "RestartSec=5\n"
        )

    def test_real_caddy_block_is_clean(self):
        self.assertClean(
            "treestock.com.au, www.treestock.com.au {\n"
            "    handle /admin/* {\n"
            "        reverse_proxy localhost:8099\n"
            "    }\n"
            "}\n"
        )


class FindingsNeverLeakTheValue(unittest.TestCase):
    def test_describe_omits_the_secret(self):
        # describe() is what lands in the log and the alert email. If it echoed
        # the line, the gate would leak the credential into a second place while
        # congratulating itself for catching it.
        findings = config_scan.scan_text("POSTGRES_PASSWORD=hunter2correcthorse", source="compose")
        self.assertEqual(len(findings), 1)
        described = findings[0].describe()
        self.assertNotIn("hunter2correcthorse", described)
        self.assertIn("POSTGRES_PASSWORD", described)
        self.assertIn("compose", described)


class CommandLine(unittest.TestCase):
    def test_exit_1_on_finding_and_0_on_clean(self):
        import subprocess
        import sys
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dirty = Path(tmp) / "dirty.env"
            dirty.write_text("API_KEY=abcdef0123456789\n")
            clean = Path(tmp) / "clean.env"
            clean.write_text("BASE_URL=https://example.com\n")

            dirty_run = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(dirty)], capture_output=True, text=True
            )
            self.assertEqual(dirty_run.returncode, 1)
            self.assertIn("API_KEY", dirty_run.stdout)
            self.assertNotIn("abcdef0123456789", dirty_run.stdout)

            clean_run = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(clean)], capture_output=True, text=True
            )
            self.assertEqual(clean_run.returncode, 0)
            self.assertEqual(clean_run.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
