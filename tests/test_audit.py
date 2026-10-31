import json
import os
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "bin", "dotenv-roundtrip-audit")
TOOL = os.path.abspath(TOOL)


def run(args, stdin=None):
    return subprocess.run([sys.executable, TOOL] + args,
                          capture_output=True, text=True)


class ParseValueTests(unittest.TestCase):
    def test_double_quoted_ok_cli(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write('A="hello"\n')
            p = f.name
        r = run([p, "--json"])
        os.unlink(p)
        d = json.loads(r.stdout)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(d["corrupt_count"], 0)


class BehaviorTests(unittest.TestCase):
    def test_clean_simple(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("A=hello\n")
            f.write("B=world\n")
            p = f.name
        r = run([p, "--json"])
        os.unlink(p)
        d = json.loads(r.stdout)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(d["corrupt_count"], 0)
        self.assertEqual(d["total_keys"], 2)

    def test_apostrophe_roundtrip_mismatch(self):
        # What write_env writes for a value containing an apostrophe:
        # KEY='It'\''s fine'  -> dotenv readers keep backslash, shell strips it
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("MSG='It'\\''s fine'\n")
            p = f.name
        r = run([p, "--json"])
        os.unlink(p)
        d = json.loads(r.stdout)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(d["corrupt_count"], 1)
        self.assertEqual(d["corruptions"][0]["kind"], "roundtrip-mismatch")

    def test_unterminated_multiline(self):
        # write_env with a newline value -> unterminated single quote
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("PEM='line1\nline2'\n")
            p = f.name
        r = run([p, "--json"])
        os.unlink(p)
        d = json.loads(r.stdout)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(d["corruptions"][0]["kind"], "unterminated-multiline")

    def test_exit_code_usage_error(self):
        r = run([])
        self.assertEqual(r.returncode, 2)

    def test_missing_file_usage_error(self):
        r = run(["/nonexistent/nope.env"])
        self.assertEqual(r.returncode, 2)

    def test_double_quoted_escaped_ok(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write('A="a\\nb"\n')
            p = f.name
        r = run([p, "--json"])
        os.unlink(p)
        d = json.loads(r.stdout)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(d["corrupt_count"], 0)

    def test_mixed_ok_and_bad(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("OK=plain\n")
            f.write("BAD='a'\\''b'\n")
            p = f.name
        r = run([p, "--json"])
        os.unlink(p)
        d = json.loads(r.stdout)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(d["corrupt_count"], 1)
        self.assertEqual(d["total_keys"], 2)

    def test_hash_dollar_inside_quotes(self):
        # 'a$b#c' as a single-quoted dotenv literal is fine for both readers
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("KEY='a$b#c'\n")
            p = f.name
        r = run([p, "--json"])
        os.unlink(p)
        d = json.loads(r.stdout)
        self.assertEqual(d["corrupt_count"], 0)

    def test_comment_and_blank_lines_ignored(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("# comment\n\nOK=hello\n")
            p = f.name
        r = run([p])
        os.unlink(p)
        self.assertEqual(r.returncode, 0)
        self.assertIn("ok: 1 key(s) round-trip cleanly", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)