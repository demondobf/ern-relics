# Development tools

Run commands from the repository root. See the [development guide](../docs/development.md)
for prerequisites and the full setup and verification procedures.

Use the native tools for individual operations:

```powershell
uv run --no-sync ruff check .
uv run --no-sync ruff format .
uv run --no-sync clang-format -i src/relics/relic_validator.cpp
./tools/setup/shell.ps1
cmake --workflow --preset release
```

Use `cmake --list-presets=all` to discover native configure, build, test, and
workflow presets. `cmake --build --preset release` builds an existing configured
tree, and `ctest --preset release` runs its tests. `debug` and `asan` are also
available. Native presets reuse `.build/<preset>/`.

Python modules combine project-specific operations where needed:

- `uv run --no-sync python -m tools.format --fix` formats all Python and C++ source files.
- `uv run --no-sync python -m tools.build.package --label dev` builds, tests, and
  validates a runnable package from the activated native shell.
- `uv run --no-sync python -m tools.check --label dev` also checks lint, formatting,
  and static analysis.

Run `uv sync --locked` before these commands. `--no-sync` prevents implicit
dependency installation. Native and Python build commands reuse `.build/<preset>/`
unless `--build-directory` is supplied. Release verification uses a private fresh
build and candidate by default. Versioned releases are never replaced.

Supporting tools are grouped by purpose:

| Directory | Responsibility | Files |
| --- | --- | --- |
| `setup/` | Separate Python installers for LLVM and native sources. PowerShell handles early diagnostics and native-shell activation. | `llvm.py`, `sources.py`, `doctor.ps1`, `shell.ps1` |
| `build/` | Coordinate native build/test/package operations, verify the host, and manage staged output with bounded cleanup. | `package.py`, `verify.py`, `output.py` |
| `checks/` | Run static analysis and checks for layout, source assets, compilation, and notices. | `analyze.py`, `source_assets.py`, Python check modules |
| `release/` | Share one package manifest, create release ZIPs/checksums, and validate provenance. | `build.py`, `package.py`, `source.py`, `manifest.py` |
| `ci/` | Select CI checks from the changed files. | `changes.py` |
| `assets/` | Extract and audit locally supplied game data. | `extract.py`, `verify_assets.py`, `verify_regulation.py` |
| `game/` | Back up explicit saves, launch an offline test profile, and run game diagnostics. | `backup_saves.py`, `launch_test.py`, `probe.py`, `verify_refresh.py` |

`process.py` provides argument-list subprocesses and tool lookup in the current
Python environment. Ordinary commands stream output as they run; commands that
parse output request capture explicitly. Python commands never activate or modify
the caller's shell.

Setup uses separate commands, followed by an offline, read-only diagnosis:

```powershell
uv sync --locked
uv run --no-sync python -m tools.setup.llvm
uv run --no-sync python -m tools.setup.sources
./tools/setup/doctor.ps1
```

Activate `./tools/setup/shell.ps1` before native builds. Create a release locally
with `uv run --no-sync python -m tools.release.build`. Each Python command exposes
`--help`. Doctor stays offline and read-only and can report missing Python or uv before
the Python environment works.

Tests live under `tests/tooling/` and `tests/integration/` and use Python's standard
library. Doctor and shell activation retain PowerShell tests. Keep
downloaded tools, checkouts, game data, saves, and journals out of packages. The
game test helper writes profiles and logs under `output/game-test/`, outside
replaceable package output.
