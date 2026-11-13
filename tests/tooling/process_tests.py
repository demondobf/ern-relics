"""Exercise real child processes: literal arguments, diagnostics, and exit status."""

import contextlib
import io
import json
import subprocess
import sys
import unittest

from tools.process import cli, run


class ProcessTests(unittest.TestCase):
    def test_arguments_are_literal_and_output_is_visible(self):
        arguments = ['a b', '[file]', '$(literal)', 'quote"inside', 'x&y']
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run(
                [
                    sys.executable,
                    '-c',
                    'import json,sys; print(json.dumps(sys.argv[1:]))',
                    *arguments,
                ]
            )
        self.assertEqual(json.loads(output.getvalue()), arguments)

    def test_failure_diagnostics_are_printed_once_and_exit_is_preserved(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                cli(
                    lambda: run(
                        [
                            sys.executable,
                            '-c',
                            'import sys; print("build output"); '
                            'print("compiler failure", file=sys.stderr); sys.exit(7)',
                        ]
                    )
                )
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(stdout.getvalue(), 'build output\n')
        self.assertEqual(stderr.getvalue().count('compiler failure\n'), 1)
        self.assertIn('exit status 7', stderr.getvalue())

    def test_explicit_capture_leaves_diagnostics_for_the_caller(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = run(
                [sys.executable, '-c', 'import sys; print("captured"); sys.exit(3)'],
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, 'captured\n')
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')
        with self.assertRaises(subprocess.CalledProcessError):
            run([sys.executable, '-c', 'raise SystemExit(3)'], capture_output=True)

    def test_cli_publishes_captured_failure_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli(
                    lambda: run(
                        [sys.executable, '-c', 'print("extraction failed"); raise SystemExit(2)'],
                        capture_output=True,
                    )
                )
        self.assertEqual(output.getvalue(), 'extraction failed\n')


if __name__ == '__main__':
    unittest.main()
