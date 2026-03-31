# Repo Guide

## Purpose

`AGENTS.md` is the instruction file Codex reads from a project or Codex home directory to learn repo-specific working rules, constraints, and preferences before it edits code.

This repo builds a Codex `AGENTS.md` from checked-in base instruction fragments plus optional local extra instructions, then syncs the selected model and multi-agent flag into Codex `config.toml`.

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

- For non-interactive smoke tests, run `python3 config_codex.py --all`.
- If you change config parsing, output rendering, or README-described behavior, update `README.md` in the same change.
