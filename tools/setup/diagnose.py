"""Report installed prerequisites as JSON without installing or modifying anything."""

import argparse
import json
import subprocess

from tools.process import ROOT, cli
from tools.setup.native import clang_tidy, llvm_directory, seven_zip
from tools.setup.sources import check_checkout, locked_sources


def diagnose(root=ROOT):
    results = []

    def inspect(name, probe, repair):
        try:
            detail = str(probe())
            ok = True
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            detail = str(error)
            ok = False
            if isinstance(error, subprocess.CalledProcessError) and error.stderr:
                detail += '\n' + error.stderr.strip()
        results.append({'name': name, 'ok': ok, 'detail': detail, 'repair': repair})

    inspect('7-Zip for LLVM setup', seven_zip, 'Install 7-Zip to extract LLVM.')
    inspect(
        'LLVM analyzer and builtin headers',
        lambda: clang_tidy(root),
        f'Run uv run --no-sync python -m tools.setup.llvm. If {llvm_directory(root)} exists, remove the incomplete installation first.',
    )
    for directory, dependency in locked_sources(root):
        inspect(
            dependency['Name'],
            lambda directory=directory, dependency=dependency: check_checkout(
                directory, dependency
            ),
            'Review checkout problems above, then run uv run --no-sync python -m tools.setup.sources.',
        )
    return results


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(diagnose()))


if __name__ == '__main__':
    cli(main)
