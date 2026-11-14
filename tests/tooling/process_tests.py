"""Exercise real child processes: literal arguments, diagnostics, and exit status."""

import contextlib
import io
import json
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

from tools.process import ROOT, cli, hidden_process, run


class ProcessTests(unittest.TestCase):
    def test_arguments_are_literal_and_output_is_visible(self):
        arguments = ['a b', '[file]', '$(literal)', 'quote"inside', 'x&y']
        result = run(
            [sys.executable, '-c', 'import json,sys; print(json.dumps(sys.argv[1:]))', *arguments],
            capture_output=True,
        )
        self.assertEqual(json.loads(result.stdout), arguments)

    def test_failure_diagnostics_are_printed_once_and_exit_is_preserved(self):
        child = 'import sys; print("build output"); print("compiler failure", file=sys.stderr); sys.exit(7)'
        result = run(
            [
                sys.executable,
                '-c',
                f'from tools.process import cli,run; import sys; cli(lambda: run([sys.executable, "-c", {child!r}]))',
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, 'build output\n')
        self.assertEqual(result.stderr.count('compiler failure\n'), 1)
        self.assertIn('exit status 7', result.stderr)

    def test_output_arrives_while_the_child_is_still_waiting(self):
        child = 'print("ready", flush=True); input(); print("done")'
        wrapper = (
            f'from tools.process import run; import sys; run([sys.executable, "-c", {child!r}])'
        )
        with (
            subprocess.Popen(
                [sys.executable, '-c', wrapper],
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                **hidden_process(),
            ) as process,
            ThreadPoolExecutor(max_workers=1) as readers,
        ):
            first_line = readers.submit(process.stdout.readline)
            try:
                self.assertEqual(first_line.result(timeout=5), 'ready\n')
                self.assertIsNone(process.poll())
            finally:
                # Unblock the child even when a buffered implementation fails this test.
                output, errors = process.communicate('\n', timeout=5)
            self.assertEqual(process.returncode, 0, errors)
            self.assertEqual(output, 'done\n')

    def test_cli_diagnostics_work_with_legacy_windows_encodings(self):
        result = run(
            [
                sys.executable,
                '-c',
                'import sys; from tools.process import cli; sys.stdout.reconfigure(encoding="ascii"); cli(lambda: print(chr(0x1f9ea)))',
            ],
            capture_output=True,
        )
        self.assertEqual(result.stdout, '\\U0001f9ea\n')

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
