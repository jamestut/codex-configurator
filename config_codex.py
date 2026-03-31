#!/usr/bin/env python3

from __future__ import annotations

import argparse
import curses
import json
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


SECTION_HEADER_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")
STATE_SELECTED_EXTRA_FILES_KEY = "selected_extra_instruction_files"


@dataclass(frozen=True)
class ModelConfig:
    name: str
    support_apply_patch: bool
    context_window: Optional[int] = None
    base_url: str = ""
    env_key: Optional[str] = None


@dataclass(frozen=True)
class AppConfig:
    codex_dir_path: Path
    models: List[ModelConfig]
    skills_path: Optional[Path] = None


@dataclass
class ExtraInstruction:
    index: int
    path: Path
    title: str
    selected: bool = False


@dataclass
class Skill:
    path: Path
    name: str
    selected: bool = False


@dataclass(frozen=True)
class CodexState:
    model_name: Optional[str]
    multi_agent_enabled: bool
    selected_extra_instruction_files: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Selection:
    model: ModelConfig
    multi_agent_enabled: bool
    skills: List[Skill]
    extra_instructions: List[ExtraInstruction]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an AGENTS.md file from base and extra instructions."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "use current defaults, include all extra instructions, and enable all "
            "valid skills without opening the TUI"
        ),
    )
    return parser.parse_args()


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def parse_config(config_path: Path) -> AppConfig:
    if not config_path.is_file():
        raise SystemExit(
            f"Error: Configuration file '{config_path}' not found.\n"
            "Create config.json from config.example.json and try again."
        )

    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: Could not parse '{config_path}': {exc}") from exc

    if not isinstance(raw_config, dict):
        raise SystemExit("Error: config.json must contain a JSON object.")

    raw_codex_dir = raw_config.get("codex_dir_path", "~/.codex")
    if raw_codex_dir is None:
        raw_codex_dir = "~/.codex"
    if not isinstance(raw_codex_dir, str) or not raw_codex_dir.strip():
        raise SystemExit("Error: 'codex_dir_path' must be a non-empty string when provided.")

    raw_skills_path = raw_config.get("skills_path")
    if raw_skills_path is not None:
        if not isinstance(raw_skills_path, str) or not raw_skills_path.strip():
            raise SystemExit("Error: 'skills_path' must be a non-empty string when provided.")
        raw_skills_path = raw_skills_path.strip()

    raw_models = raw_config.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise SystemExit("Error: 'models' must be a non-empty array.")

    models: List[ModelConfig] = []
    seen_names = set()
    for index, raw_model in enumerate(raw_models, start=1):
        if not isinstance(raw_model, dict):
            raise SystemExit(f"Error: models[{index}] must be an object.")

        name = raw_model.get("name")
        support_apply_patch = raw_model.get("support_apply_patch")
        context_window = raw_model.get("context_window")
        base_url = raw_model.get("base_url")
        env_key = raw_model.get("env_key")

        if not isinstance(name, str) or not name.strip():
            raise SystemExit(f"Error: models[{index}].name must be a non-empty string.")
        if name in seen_names:
            raise SystemExit(f"Error: Duplicate model name '{name}' in config.json.")
        if not isinstance(support_apply_patch, bool):
            raise SystemExit(
                f"Error: models[{index}].support_apply_patch must be true or false."
            )
        if context_window is not None:
            if isinstance(context_window, bool) or not isinstance(context_window, int):
                raise SystemExit(
                    f"Error: models[{index}].context_window must be an integer when provided."
                )
            if context_window <= 0:
                raise SystemExit(
                    f"Error: models[{index}].context_window must be greater than zero."
                )
        if not isinstance(base_url, str) or not base_url.strip():
            raise SystemExit(
                f"Error: models[{index}].base_url must be a non-empty string."
            )
        base_url = base_url.strip()
        if env_key is not None:
            if not isinstance(env_key, str) or not env_key.strip():
                raise SystemExit(
                    f"Error: models[{index}].env_key must be a non-empty string when provided."
                )
            env_key = env_key.strip()

        models.append(
            ModelConfig(
                name=name,
                support_apply_patch=support_apply_patch,
                context_window=context_window,
                base_url=base_url,
                env_key=env_key,
            )
        )
        seen_names.add(name)

    return AppConfig(
        codex_dir_path=Path(raw_codex_dir).expanduser(),
        models=models,
        skills_path=Path(raw_skills_path).expanduser() if raw_skills_path else None,
    )


def load_extra_instructions(extra_dir: Path) -> List[ExtraInstruction]:
    if not extra_dir.exists():
        return []
    if not extra_dir.is_dir():
        raise SystemExit(f"Error: '{extra_dir}' exists but is not a directory.")

    instructions: List[ExtraInstruction] = []
    for index, path in enumerate(sorted(extra_dir.glob("*.md")), start=1):
        lines = path.read_text(encoding="utf-8").splitlines()
        first_line = lines[0].strip() if lines else ""
        if not first_line.startswith("# "):
            raise SystemExit(
                "Error: Extra instruction file "
                f"'{path}' must begin with a '# ' heading subject line."
            )
        instructions.append(
            ExtraInstruction(index=index, path=path, title=first_line[2:].strip())
        )

    return instructions


def load_skills(skills_dir: Optional[Path]) -> List[Skill]:
    if skills_dir is None:
        return []
    if not skills_dir.exists():
        return []
    if not skills_dir.is_dir():
        raise SystemExit(f"Error: '{skills_dir}' exists but is not a directory.")

    skills: List[Skill] = []
    skill_paths = sorted(path for path in skills_dir.iterdir() if path.is_dir())
    for path in skill_paths:
        if not (path / "SKILL.md").is_file():
            continue
        skills.append(
            Skill(
                path=path.resolve(),
                name=path.name,
            )
        )

    return skills


def parse_toml_state(config_toml_path: Path) -> CodexState:
    if not config_toml_path.is_file():
        return CodexState(model_name=None, multi_agent_enabled=False)

    model_name: Optional[str] = None
    multi_agent_enabled = False
    current_section: Optional[str] = None

    for raw_line in config_toml_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        section_match = SECTION_HEADER_RE.match(stripped)
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        key_value = parse_toml_key_value(stripped)
        if key_value is None:
            continue

        key, value = key_value
        if current_section is None and key == "model":
            parsed = parse_toml_string(value)
            if parsed is not None:
                model_name = parsed
        elif current_section == "features" and key == "multi_agent":
            parsed = parse_toml_bool(value)
            if parsed is not None:
                multi_agent_enabled = parsed

    return CodexState(
        model_name=model_name,
        multi_agent_enabled=multi_agent_enabled,
    )


def load_json_state(state_json_path: Path, codex_state: CodexState) -> CodexState:
    return CodexState(
        model_name=codex_state.model_name,
        multi_agent_enabled=codex_state.multi_agent_enabled,
        selected_extra_instruction_files=load_selected_extra_instruction_files(
            state_json_path
        ),
    )


def load_selected_extra_instruction_files(state_json_path: Path) -> Tuple[str, ...]:
    if not state_json_path.is_file():
        return ()

    try:
        raw_state = json.loads(state_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    if not isinstance(raw_state, dict):
        return ()

    raw_selected = raw_state.get(STATE_SELECTED_EXTRA_FILES_KEY)
    if not isinstance(raw_selected, list):
        return ()

    selected_files: List[str] = []
    seen_files: set[str] = set()
    for value in raw_selected:
        if not isinstance(value, str):
            continue
        file_name = Path(value).name.strip()
        if not file_name or file_name in seen_files:
            continue
        selected_files.append(file_name)
        seen_files.add(file_name)

    return tuple(selected_files)


def write_json_state(
    state_json_path: Path,
    selected_extra_instruction_files: Sequence[str],
) -> None:
    unique_files: List[str] = []
    seen_files: set[str] = set()
    for value in selected_extra_instruction_files:
        file_name = Path(value).name.strip()
        if not file_name or file_name in seen_files:
            continue
        unique_files.append(file_name)
        seen_files.add(file_name)

    state_json_path.parent.mkdir(parents=True, exist_ok=True)
    state_json_path.write_text(
        json.dumps(
            {STATE_SELECTED_EXTRA_FILES_KEY: unique_files},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def apply_saved_extra_instruction_selection(
    extra_instructions: Sequence[ExtraInstruction],
    selected_extra_instruction_files: Sequence[str],
) -> None:
    selected_file_names = set(selected_extra_instruction_files)
    for instruction in extra_instructions:
        instruction.selected = instruction.path.name in selected_file_names


def apply_saved_skill_selection(
    skills: Sequence[Skill],
    enabled_skills_dir: Path,
) -> None:
    if not skills or not enabled_skills_dir.is_dir():
        return

    skill_targets = {skill.name: skill.path.resolve() for skill in skills}
    for path in enabled_skills_dir.iterdir():
        if not path.is_symlink():
            continue

        expected_target = skill_targets.get(path.name)
        if expected_target is None:
            continue

        try:
            if path.resolve() == expected_target:
                for skill in skills:
                    if skill.name == path.name:
                        skill.selected = True
                        break
        except OSError:
            continue


def parse_toml_key_value(stripped_line: str) -> Optional[Tuple[str, str]]:
    if "=" not in stripped_line:
        return None
    key, value = stripped_line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, strip_inline_comment(value.strip())


def strip_inline_comment(value: str) -> str:
    in_string = False
    escaped = False
    result: List[str] = []

    for char in value:
        if char == "\\" and in_string and not escaped:
            escaped = True
            result.append(char)
            continue
        if char == '"' and not escaped:
            in_string = not in_string
        if char == "#" and not in_string:
            break
        result.append(char)
        escaped = False

    return "".join(result).strip()


def parse_toml_string(value: str) -> Optional[str]:
    if len(value) < 2 or not (value.startswith('"') and value.endswith('"')):
        return None
    inner = value[1:-1]
    return bytes(inner, "utf-8").decode("unicode_escape")


def parse_toml_bool(value: str) -> Optional[bool]:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def choose_default_model(config: AppConfig, codex_state: CodexState) -> ModelConfig:
    if codex_state.model_name:
        for model in config.models:
            if model.name == codex_state.model_name:
                return model
    return config.models[0]


class BuilderUI:
    def __init__(
        self,
        models: Sequence[ModelConfig],
        default_model_name: str,
        skills: Sequence[Skill],
        show_skills: bool,
        extra_instructions: Sequence[ExtraInstruction],
        multi_agent_enabled: bool,
        target_path: Path,
    ) -> None:
        self.models = list(models)
        self.model_index = next(
            index
            for index, model in enumerate(self.models)
            if model.name == default_model_name
        )
        self.skills = list(skills)
        self.show_skills = show_skills
        self.extra_instructions = list(extra_instructions)
        self.multi_agent_enabled = multi_agent_enabled
        self.target_path = target_path
        self.cursor = 0
        self.offset = 0
        self.highlight_attr = curses.A_REVERSE

    def run(self) -> Optional[Selection]:
        return curses.wrapper(self._main)

    def _main(self, stdscr: "curses._CursesWindow") -> Optional[Selection]:
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        stdscr.keypad(True)
        self._configure_colors()

        while True:
            self._draw(stdscr)
            key = stdscr.getch()

            if key in (ord("q"), ord("Q"), 27):
                return None
            if key in (curses.KEY_ENTER, 10, 13):
                if self.cursor == 0:
                    self._open_model_dialog(stdscr)
                    continue
                if self.show_skills and self.cursor == self._skills_row_index():
                    self._open_skills_dialog(stdscr)
                    continue
                return Selection(
                    model=self.models[self.model_index],
                    multi_agent_enabled=self.multi_agent_enabled,
                    skills=[skill for skill in self.skills if skill.selected],
                    extra_instructions=[
                        instruction
                        for instruction in self.extra_instructions
                        if instruction.selected
                    ],
                )
            if key in (curses.KEY_UP, ord("k"), ord("K")):
                self.cursor = max(0, self.cursor - 1)
            elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
                self.cursor = min(self._row_count() - 1, self.cursor + 1)
            elif key == curses.KEY_PPAGE:
                self.cursor = max(0, self.cursor - self._page_size(stdscr))
            elif key == curses.KEY_NPAGE:
                self.cursor = min(self._row_count() - 1, self.cursor + self._page_size(stdscr))
            elif key == ord(" "):
                self._toggle_current_row()
            elif key in (ord("a"), ord("A")):
                for instruction in self.extra_instructions:
                    instruction.selected = True
            elif key in (ord("n"), ord("N")):
                for instruction in self.extra_instructions:
                    instruction.selected = False

    def _row_count(self) -> int:
        return self._extra_row_start() + len(self.extra_instructions)

    def _skills_row_index(self) -> int:
        return 2

    def _extra_row_start(self) -> int:
        return 3 if self.show_skills else 2

    def _page_size(self, stdscr: "curses._CursesWindow") -> int:
        height, width = stdscr.getmaxyx()
        return max(1, height - self._header_height(width) - 2)

    def _header_lines(self, width: int) -> List[str]:
        wrap_width = max(20, width - 4)
        lines = [
            "AGENTS.md Generator",
            *textwrap.wrap(f"Target: {self.target_path}", wrap_width),
            (
                "Up/down move, Enter on Model opens search, "
                "Enter on Skills manages skills, space toggle"
                if self.show_skills
                else "Up/down move, Enter on Model opens search, space toggle"
            ),
            "Enter elsewhere confirm, q cancel",
            "a select all extras, n clear all extras",
            "",
        ]
        return lines

    def _header_height(self, width: int) -> int:
        return len(self._header_lines(width))

    def _toggle_current_row(self) -> None:
        if self.cursor == 1:
            self.multi_agent_enabled = not self.multi_agent_enabled
            return
        if self.cursor >= self._extra_row_start():
            instruction = self.extra_instructions[self.cursor - self._extra_row_start()]
            instruction.selected = not instruction.selected

    def _rows(self) -> List[str]:
        model = self.models[self.model_index]
        rows = [
            f"Model: {model.name} (press Enter to search)",
            f"[{'x' if self.multi_agent_enabled else ' '}] Enable multi agent",
        ]
        if self.show_skills:
            selected_skill_count = sum(skill.selected for skill in self.skills)
            rows.append(
                f"Skills: {selected_skill_count}/{len(self.skills)} selected "
                "(press Enter to manage)"
            )
        for instruction in self.extra_instructions:
            marker = "x" if instruction.selected else " "
            rows.append(f"[{marker}] {instruction.index}. {instruction.title}")
        return rows

    def _open_model_dialog(self, stdscr: "curses._CursesWindow") -> None:
        query = ""
        active_index = self.model_index
        offset = 0

        while True:
            filtered_indexes = self._filtered_model_indexes(query)
            if filtered_indexes and active_index not in filtered_indexes:
                active_index = filtered_indexes[0]

            active_position = (
                filtered_indexes.index(active_index)
                if filtered_indexes and active_index in filtered_indexes
                else 0
            )
            offset = self._draw_model_dialog(
                stdscr=stdscr,
                query=query,
                filtered_indexes=filtered_indexes,
                active_position=active_position,
                offset=offset,
            )
            key = stdscr.getch()

            if key in (ord("q"), ord("Q"), 27):
                return
            if key in (curses.KEY_ENTER, 10, 13):
                if filtered_indexes:
                    self.model_index = active_index
                    return
            elif key in (curses.KEY_UP, ord("k"), ord("K")) and filtered_indexes:
                active_position = max(0, active_position - 1)
                active_index = filtered_indexes[active_position]
            elif key in (curses.KEY_DOWN, ord("j"), ord("J")) and filtered_indexes:
                active_position = min(len(filtered_indexes) - 1, active_position + 1)
                active_index = filtered_indexes[active_position]
            elif key == curses.KEY_PPAGE and filtered_indexes:
                page_size = self._dialog_page_size(stdscr)
                active_position = max(0, active_position - page_size)
                active_index = filtered_indexes[active_position]
            elif key == curses.KEY_NPAGE and filtered_indexes:
                page_size = self._dialog_page_size(stdscr)
                active_position = min(len(filtered_indexes) - 1, active_position + page_size)
                active_index = filtered_indexes[active_position]
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                query = query[:-1]
            elif 32 <= key <= 126:
                query += chr(key)

    def _open_skills_dialog(self, stdscr: "curses._CursesWindow") -> None:
        selected_names = {skill.name for skill in self.skills if skill.selected}
        active_position = 0
        offset = 0

        while True:
            offset = self._draw_skills_dialog(
                stdscr=stdscr,
                active_position=active_position,
                offset=offset,
                selected_names=selected_names,
            )
            key = stdscr.getch()

            if key in (ord("q"), ord("Q"), 27):
                return
            if key in (curses.KEY_ENTER, 10, 13):
                for skill in self.skills:
                    skill.selected = skill.name in selected_names
                return
            if key in (curses.KEY_UP, ord("k"), ord("K")) and self.skills:
                active_position = max(0, active_position - 1)
            elif key in (curses.KEY_DOWN, ord("j"), ord("J")) and self.skills:
                active_position = min(len(self.skills) - 1, active_position + 1)
            elif key == curses.KEY_PPAGE and self.skills:
                active_position = max(0, active_position - self._dialog_page_size(stdscr))
            elif key == curses.KEY_NPAGE and self.skills:
                active_position = min(
                    len(self.skills) - 1,
                    active_position + self._dialog_page_size(stdscr),
                )
            elif key == ord(" ") and self.skills:
                skill_name = self.skills[active_position].name
                if skill_name in selected_names:
                    selected_names.remove(skill_name)
                else:
                    selected_names.add(skill_name)
            elif key in (ord("a"), ord("A")):
                selected_names = {skill.name for skill in self.skills}
            elif key in (ord("n"), ord("N")):
                selected_names = set()

    def _filtered_model_indexes(self, query: str) -> List[int]:
        if not query:
            return list(range(len(self.models)))

        normalized_query = query.lower()
        return [
            index
            for index, model in enumerate(self.models)
            if normalized_query in model.name.lower()
        ]

    def _dialog_page_size(self, stdscr: "curses._CursesWindow") -> int:
        height, _ = stdscr.getmaxyx()
        return max(1, min(8, height - 10))

    def _draw_model_dialog(
        self,
        stdscr: "curses._CursesWindow",
        query: str,
        filtered_indexes: Sequence[int],
        active_position: int,
        offset: int,
    ) -> int:
        self._draw(stdscr)
        height, width = stdscr.getmaxyx()

        page_size = self._dialog_page_size(stdscr)
        offset = min(offset, max(0, len(filtered_indexes) - page_size))
        if filtered_indexes:
            if active_position < offset:
                offset = active_position
            elif active_position >= offset + page_size:
                offset = active_position - page_size + 1
        else:
            offset = 0

        list_rows = max(1, min(page_size, len(filtered_indexes) or 1))
        max_dialog_height = max(6, height - 2)
        max_dialog_width = max(20, width - 2)
        dialog_height = min(max_dialog_height, max(8, list_rows + 6))
        dialog_width = min(max_dialog_width, 72)
        top = max(0, (height - dialog_height) // 2)
        left = max(0, (width - dialog_width) // 2)

        dialog = curses.newwin(dialog_height, dialog_width, top, left)
        dialog.keypad(True)
        dialog.erase()
        dialog.box()

        title = "Select model"
        search_label = f"Search: {query}" if query else "Search: "
        help_line = "Type to filter, Enter choose, Esc cancel"
        dialog.addnstr(1, 2, title, dialog_width - 4, curses.A_BOLD)
        dialog.addnstr(2, 2, search_label, dialog_width - 4)
        dialog.addnstr(3, 2, help_line, dialog_width - 4)

        list_top = 4
        if filtered_indexes:
            for row in range(list_rows):
                model_position = offset + row
                if model_position >= len(filtered_indexes):
                    break
                model = self.models[filtered_indexes[model_position]]
                attr = self.highlight_attr if model_position == active_position else curses.A_NORMAL
                dialog.addnstr(list_top + row, 2, model.name, dialog_width - 4, attr)
        else:
            dialog.addnstr(list_top, 2, "No models match your search.", dialog_width - 4)

        status = f"{len(filtered_indexes)} match{'es' if len(filtered_indexes) != 1 else ''}"
        dialog.addnstr(dialog_height - 2, 2, status, dialog_width - 4)
        dialog.refresh()
        return offset

    def _draw_skills_dialog(
        self,
        stdscr: "curses._CursesWindow",
        active_position: int,
        offset: int,
        selected_names: set[str],
    ) -> int:
        self._draw(stdscr)
        height, width = stdscr.getmaxyx()

        page_size = self._dialog_page_size(stdscr)
        offset = min(offset, max(0, len(self.skills) - page_size))
        if self.skills:
            if active_position < offset:
                offset = active_position
            elif active_position >= offset + page_size:
                offset = active_position - page_size + 1
        else:
            offset = 0

        list_rows = max(1, min(page_size, len(self.skills) or 1))
        max_dialog_height = max(6, height - 2)
        max_dialog_width = max(20, width - 2)
        dialog_height = min(max_dialog_height, max(8, list_rows + 6))
        dialog_width = min(max_dialog_width, 72)
        top = max(0, (height - dialog_height) // 2)
        left = max(0, (width - dialog_width) // 2)

        dialog = curses.newwin(dialog_height, dialog_width, top, left)
        dialog.keypad(True)
        dialog.erase()
        dialog.box()

        dialog.addnstr(1, 2, "Manage skills", dialog_width - 4, curses.A_BOLD)
        dialog.addnstr(
            2,
            2,
            "Space toggle, a all, n none, Enter save, Esc cancel",
            dialog_width - 4,
        )

        list_top = 4
        if self.skills:
            for row in range(list_rows):
                skill_position = offset + row
                if skill_position >= len(self.skills):
                    break
                skill = self.skills[skill_position]
                marker = "x" if skill.name in selected_names else " "
                line = f"[{marker}] {skill.name}"
                attr = (
                    self.highlight_attr
                    if skill_position == active_position
                    else curses.A_NORMAL
                )
                dialog.addnstr(list_top + row, 2, line, dialog_width - 4, attr)
        else:
            dialog.addnstr(list_top, 2, "No valid skills found.", dialog_width - 4)

        selected_count = len(selected_names)
        status = f"{selected_count}/{len(self.skills)} skills selected"
        dialog.addnstr(dialog_height - 2, 2, status, dialog_width - 4)
        dialog.refresh()
        return offset

    def _draw(self, stdscr: "curses._CursesWindow") -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        header_lines = self._header_lines(width)
        rows = self._rows()
        page_size = max(1, height - len(header_lines) - 2)

        self.offset = min(self.offset, max(0, len(rows) - page_size))
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + page_size:
            self.offset = self.cursor - page_size + 1

        for row, line in enumerate(header_lines):
            stdscr.addnstr(row, 0, line, width - 1)

        for row in range(page_size):
            row_index = self.offset + row
            if row_index >= len(rows):
                break
            attr = self.highlight_attr if row_index == self.cursor else curses.A_NORMAL
            stdscr.addnstr(len(header_lines) + row, 0, rows[row_index], width - 1, attr)

        selected_count = sum(
            instruction.selected for instruction in self.extra_instructions
        )
        footer_parts: List[str] = []
        if self.show_skills:
            if self.skills:
                selected_skill_count = sum(skill.selected for skill in self.skills)
                footer_parts.append(
                    f"{selected_skill_count}/{len(self.skills)} skills selected"
                )
            else:
                footer_parts.append("No skills found")
        if self.extra_instructions:
            footer_parts.append(
                f"{selected_count}/{len(self.extra_instructions)} extras selected"
            )
        else:
            footer_parts.append("No extra instructions found")
        footer = " | ".join(footer_parts)
        stdscr.addnstr(height - 1, 0, footer, width - 1)
        stdscr.refresh()

    def _configure_colors(self) -> None:
        if not curses.has_colors():
            return

        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            return

        try:
            curses.init_pair(1, -1, -1)
            self.highlight_attr = curses.color_pair(1) | curses.A_REVERSE
        except curses.error:
            self.highlight_attr = curses.A_REVERSE


def choose_selection(
    config: AppConfig,
    codex_state: CodexState,
    skills: Sequence[Skill],
    extra_instructions: Sequence[ExtraInstruction],
    enabled_skills_dir: Path,
    target_path: Path,
    select_all: bool,
) -> Optional[Selection]:
    default_model = choose_default_model(config, codex_state)
    if select_all:
        return Selection(
            model=default_model,
            multi_agent_enabled=codex_state.multi_agent_enabled,
            skills=list(skills),
            extra_instructions=list(extra_instructions),
        )

    apply_saved_extra_instruction_selection(
        extra_instructions,
        codex_state.selected_extra_instruction_files,
    )
    apply_saved_skill_selection(skills, enabled_skills_dir)

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Error: An interactive terminal is required unless you pass --all.")

    try:
        return BuilderUI(
            models=config.models,
            default_model_name=default_model.name,
            skills=skills,
            show_skills=config.skills_path is not None,
            extra_instructions=extra_instructions,
            multi_agent_enabled=codex_state.multi_agent_enabled,
            target_path=target_path,
        ).run()
    except curses.error as exc:
        raise SystemExit(f"Error: Could not start the TUI: {exc}") from exc


def build_sections(
    base_dir: Path,
    selection: Selection,
) -> List[Path]:
    sections = [base_dir / "base_instructions" / "general.md"]
    if not selection.model.support_apply_patch:
        sections.append(base_dir / "base_instructions" / "apply_patch.md")
    if selection.multi_agent_enabled:
        sections.append(base_dir / "base_instructions" / "multi_agent.md")
    sections.extend(instruction.path for instruction in selection.extra_instructions)
    return sections


def render_sections(section_paths: Sequence[Path]) -> str:
    rendered_parts = [
        section_path.read_text(encoding="utf-8").rstrip("\n")
        for section_path in section_paths
    ]
    return "\n\n".join(rendered_parts) + "\n"


def write_agents_output(target_path: Path, section_paths: Sequence[Path]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(render_sections(section_paths), encoding="utf-8")


def sync_selected_skills(enabled_skills_dir: Path, selected_skills: Sequence[Skill]) -> None:
    if enabled_skills_dir.exists() and not enabled_skills_dir.is_dir():
        raise SystemExit(
            f"Error: Skills destination '{enabled_skills_dir}' exists but is not a directory."
        )

    enabled_skills_dir.mkdir(parents=True, exist_ok=True)

    selected_skills_by_name = {skill.name: skill for skill in selected_skills}
    for path in enabled_skills_dir.iterdir():
        if path.is_symlink() and path.name not in selected_skills_by_name:
            path.unlink()

    for skill_name, skill in selected_skills_by_name.items():
        destination = enabled_skills_dir / skill_name
        if destination.is_symlink():
            try:
                if destination.resolve() == skill.path:
                    continue
            except OSError:
                pass
            destination.unlink()
        elif destination.exists():
            raise SystemExit(
                f"Error: Cannot replace '{destination}' because it is not a symlink."
            )

        destination.symlink_to(skill.path)


def update_codex_config(
    config_toml_path: Path,
    model_name: str,
    context_window: Optional[int],
    base_url: str,
    env_key: Optional[str],
    multi_agent_enabled: bool,
) -> None:
    if config_toml_path.is_file():
        lines = config_toml_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    lines = upsert_top_level_key(lines, "model", f'model = "{escape_toml_string(model_name)}"')
    if context_window is None:
        lines = remove_top_level_key(lines, "model_context_window")
    else:
        lines = upsert_top_level_key(
            lines, "model_context_window", f"model_context_window = {context_window}"
        )
    lines = upsert_top_level_key(lines, "model_provider", 'model_provider = "managed"')
    lines = upsert_section_key(
        lines,
        "model_providers.managed",
        "name",
        'name = "Managed Provider"',
    )
    lines = upsert_section_key(
        lines,
        "model_providers.managed",
        "base_url",
        f'base_url = "{escape_toml_string(base_url)}"',
    )
    if env_key is None:
        lines = remove_section_key(lines, "model_providers.managed", "env_key")
    else:
        lines = upsert_section_key(
            lines,
            "model_providers.managed",
            "env_key",
            f'env_key = "{escape_toml_string(env_key)}"',
        )
    lines = upsert_section_key(
        lines,
        "features",
        "multi_agent",
        f"multi_agent = {'true' if multi_agent_enabled else 'false'}",
    )

    content = "\n".join(lines).rstrip("\n")
    if content:
        content += "\n"
    config_toml_path.parent.mkdir(parents=True, exist_ok=True)
    config_toml_path.write_text(content, encoding="utf-8")


def escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def upsert_top_level_key(lines: List[str], key: str, new_line: str) -> List[str]:
    result = list(lines)
    top_level_end = find_top_level_end(result)
    key_indexes = [
        index
        for index in range(top_level_end)
        if is_active_key_line(result[index], key)
    ]

    if key_indexes:
        result[key_indexes[0]] = new_line
        for index in reversed(key_indexes[1:]):
            del result[index]
    else:
        insert_at = top_level_end
        while insert_at > 0 and result[insert_at - 1].strip() == "":
            insert_at -= 1
        result.insert(insert_at, new_line)

    return result


def remove_top_level_key(lines: List[str], key: str) -> List[str]:
    result = list(lines)
    top_level_end = find_top_level_end(result)
    for index in reversed(range(top_level_end)):
        if is_active_key_line(result[index], key):
            del result[index]
    return result


def upsert_section_key(
    lines: List[str],
    section_name: str,
    key: str,
    new_line: str,
) -> List[str]:
    result = list(lines)
    section_range = find_section_range(result, section_name)

    if section_range is None:
        while result and result[-1].strip() == "":
            result.pop()
        if result:
            result.append("")
        result.append(f"[{section_name}]")
        result.append(new_line)
        return result

    start, end = section_range
    key_indexes = [
        index
        for index in range(start + 1, end)
        if is_active_key_line(result[index], key)
    ]
    if key_indexes:
        result[key_indexes[0]] = new_line
        for index in reversed(key_indexes[1:]):
            del result[index]
    else:
        insert_at = end
        while insert_at > start + 1 and result[insert_at - 1].strip() == "":
            insert_at -= 1
        result.insert(insert_at, new_line)

    return result


def remove_section_key(
    lines: List[str],
    section_name: str,
    key: str,
) -> List[str]:
    result = list(lines)
    section_range = find_section_range(result, section_name)
    if section_range is None:
        return result

    start, end = section_range
    for index in reversed(range(start + 1, end)):
        if is_active_key_line(result[index], key):
            del result[index]
    return result


def find_top_level_end(lines: Sequence[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if SECTION_HEADER_RE.match(stripped):
            return index
    return len(lines)


def find_section_range(lines: Sequence[str], section_name: str) -> Optional[Tuple[int, int]]:
    start: Optional[int] = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = SECTION_HEADER_RE.match(stripped)
        if not match:
            continue

        current_name = match.group(1).strip()
        if start is not None:
            return start, index
        if current_name == section_name:
            start = index

    if start is None:
        return None
    return start, len(lines)


def is_active_key_line(line: str, key: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return False
    return re.match(rf"^\s*{re.escape(key)}\s*=", line) is not None


def main() -> int:
    args = parse_args()
    base_dir = script_dir()
    state_json_path = base_dir / "state.json"
    config = parse_config(base_dir / "config.json")
    target_path = config.codex_dir_path / "AGENTS.md"
    config_toml_path = config.codex_dir_path / "config.toml"
    enabled_skills_dir = config.codex_dir_path / "skills"
    codex_state = load_json_state(state_json_path, parse_toml_state(config_toml_path))
    skills = load_skills(config.skills_path)
    extra_instructions = load_extra_instructions(base_dir / "extra_instructions")
    selection = choose_selection(
        config=config,
        codex_state=codex_state,
        skills=skills,
        extra_instructions=extra_instructions,
        enabled_skills_dir=enabled_skills_dir,
        target_path=target_path,
        select_all=args.all,
    )

    if selection is None:
        print("Cancelled.")
        return 0

    section_paths = build_sections(base_dir, selection)
    write_agents_output(target_path, section_paths)
    update_codex_config(
        config_toml_path=config_toml_path,
        model_name=selection.model.name,
        context_window=selection.model.context_window,
        base_url=selection.model.base_url,
        env_key=selection.model.env_key,
        multi_agent_enabled=selection.multi_agent_enabled,
    )
    if config.skills_path is not None:
        sync_selected_skills(enabled_skills_dir, selection.skills)
    if not args.all:
        write_json_state(
            state_json_path,
            [instruction.path.name for instruction in selection.extra_instructions],
        )

    print(f"Successfully generated {target_path}")
    print(f"Updated {config_toml_path}")
    if config.skills_path is not None:
        print(f"Synced {enabled_skills_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
