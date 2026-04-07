# jamestut's Personal Codex Configurator

This program builds `AGENTS.md` for Codex from a fixed base instruction set plus optional extra instruction files. It also keeps the selected Codex model and multi-agent setting in sync with your Codex `config.toml`, and can optionally sync selected skills into your Codex skills directory.

**Note:** This tool is specifically designed to work with **jamestut's customised Codex agent** and will cause issues with the standard Codex CLI distribution.

## Usage

Interactive mode:

```bash
python3 config_codex.py
```

Controls:

- Up/down: move between rows
- Enter on `Model`: open the searchable model picker
- Enter on `Skills`: open the skills dialog (always visible)
- Space: toggle options
- Enter: toggle options or open submenu
- `s`: confirm and save
- `q` or `Esc`: cancel
- `a`: select all (extra instructions and System skills)
- `n`: clear all (extra instructions and System skills)


## Files and folders

- `config_codex.py`: interactive builder script
- `config.json`: local configuration for available models and optional Codex directory
- `config.example.json`: example configuration
- `base_instructions/`: built-in instruction fragments
- `extra_instructions/`: optional user-selectable markdown instruction files
- `<codex_dir_path>/skills`: symlinked Codex skills managed from the optional skills selector

The generated output is always written to:

```text
<codex_dir_path>/AGENTS.md
```

If `codex_dir_path` is omitted from `config.json`, the script uses `~/.codex`.

## Config format

Create `config.json` from `config.example.json` and edit it as needed:

```json
{
  "codex_dir_path": "~/.codex",
  "skills_path": "/home/jamesn/repo/ai-tools/ai-agents-helper/codex/skills",
  "models": [
    {
      "name": "gpt-5.4",
      "support_apply_patch": true,
      "base_url": "https://litellm-proxy.example.net",
      "env_key": "OPENAI_API_KEY"
    },
    {
      "name": "gemini-3.1-pro-preview",
      "support_apply_patch": false,
      "context_window": 256000,
      "base_url": "https://litellm-proxy.example.net"
    }
  ]
}
```

Rules:

- `models` must contain at least one model.
- `skills_path` is optional.
- `name` and `base_url` are required for each model.
- `support_apply_patch` is required for each model (set to `true` for GPT models, `false` otherwise).
- `context_window` is optional.
- `env_key` is optional.

When `skills_path` is configured, the script scans its immediate child directories and treats a folder as a valid skill only when it contains `SKILL.md`.

## Extra instructions

Only `.md` files inside `extra_instructions/` are shown in the selector.

Each extra instruction file must start with a heading subject line on the first line:

```md
# My Subject Line
```

That heading text is what appears in the checklist. Files are listed in filename order.

## Skills

The main screen always shows a `Skills` row between `Enable multi agent` and the extra-instruction checklist.

Press Enter on that row to open the skills dialog. Inside the dialog:

- "System skills" is always the first item at the top of the dialog
- Space: toggle the highlighted skill
- Enter: save the skill selection and return
- `q` or `Esc`: cancel changes and return
- `a`: enable System skills and select all valid skills
- `n`: disable System skills and clear all skills

When `skills_path` is configured, skills from source directories are listed below System skills in filename order. Existing enabled skills are preselected by reading symlinks from `<codex_dir_path>/skills`.

After confirmation, the script reconciles `<codex_dir_path>/skills`:

- selected skills are symlinked to the configured source directories
- stale or unselected symlinks are removed, even if they point somewhere else
- existing non-symlink files or directories are left alone
- if a selected skill path already exists as a non-symlink, the script stops with an error instead of deleting it

## How output is built

The generated `AGENTS.md` always uses this order:

1. `base_instructions/general.md`
2. `base_instructions/apply_patch.md` only when the model has `support_apply_patch: false`
3. `base_instructions/multi_agent.md` only when `Enable multi agent` is checked
4. Checked files from `extra_instructions/`

## Codex config sync

After confirmation, the script updates `<codex_dir_path>/config.toml`:

- top-level `model` is set to the selected model
- top-level `model_context_window` is set when the chosen model defines `context_window`
- top-level `model_context_window` is removed when the chosen model does not define it
- top-level `model_provider` is set to `"managed"`
- `[model_providers.managed]` is created or updated with `name = "Managed Provider"` and the selected model's `base_url`
- `[model_providers.managed].env_key` is set when configured for the selected model and removed otherwise
- `[features].multi_agent` is set to `true` or `false`

When `config.toml` does not exist yet, the script creates a minimal one with those settings.

The initial UI defaults are loaded from `<codex_dir_path>/config.toml`:

- selected model uses top-level `model`
- if that model is not present in `config.json`, the first configured model is used
- `Enable multi agent` uses `[features].multi_agent`, defaulting to `false` when missing

Skill defaults are loaded from existing symlinks in `<codex_dir_path>/skills`.
