# Repo Guide

Main entrypoint: `config_codex.py`.

## Important Files

- `config_codex.py`: validates config, runs the TUI, renders `AGENTS.md`, and updates `config.toml`
- `base_instructions/`: checked-in instruction fragments that are concatenated into output
- `config.example.json`: tracked example config
- `README.md`: user-facing behavior and file format rules

Local-only files and directories are ignored by git:

- `config.json`
- `extra_instructions/`
- `.codex/`

## Editing Rules

- Preserve the section build order in `build_sections()` unless the product behavior is intentionally changing; update `README.md` if it does.
- Keep the extra-instruction contract intact: only `extra_instructions/*.md` files are loaded, and each must start with a first-line `# ` heading.
- Be careful when changing TOML handling. The script intentionally supports a narrow subset used for top-level `model`, optional `model_context_window`, and `[features].multi_agent`.
- Prefer small, readable changes over introducing new dependencies or a full TOML parser unless there is a clear need.

## Validation

- If you change config parsing, output rendering, or README-described behavior, update `README.md` in the same change.
- Only validate statically (e.g. type/schema checks, linting); do not run the script or execute generated output as part of validation.
