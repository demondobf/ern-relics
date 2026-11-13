# Agent instructions

See the [development guide](docs/development.md) for setup and verification.

- Activate `./tools/setup/shell.ps1`, then run
  `uv run --no-sync python -m tools.check --label dev` for code changes.
- For documentation-only changes, run `uv run --locked python -m tools.checks.layout`.
- Reuse `dist/ern-relics-<version>-dev/` for development builds. Preserve versioned
  release packages and ZIPs in `dist/`.
- Keep installed configuration, presets, and journals outside replaceable build output.
- Keep game assets, saves, extracted data, and proprietary decoders out of version
  control and distributed packages.
