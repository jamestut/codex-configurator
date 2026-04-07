# apply_patch

## Syntax Recap

```
*** Begin Patch
*** Add File: path    # + lines only
*** Delete File: path # nothing follows
*** Update File: path # hunks with context
*** Move to: newpath  # optional, after Update header
@@ optional header    # hunk start
 context line         # space prefix
-removed line         # minus prefix
+added line           # plus prefix
*** End of File       # optional hunk end
*** End Patch
```

## Critical Rules

1. **Every patch needs at least one `+` or `-` line.** A hunk that is all context lines (space-prefixed) will silently succeed but change nothing.

2. **`-` means "remove this exact line".** Do not use `-` just to frame context. If you include a line starting with `-`, it must exist in the file and will be deleted.

3. **Whitespace is exact.** The tool compares context and removal lines literally - spaces, tabs, blank lines must match the file byte-for-byte.

> **Warning: Space-count drift is the #1 cause of silent breakage.**
> When writing `+` lines, models frequently drop one leading space from the original indentation. A line that is indented by 4 spaces in the file must appear in the patch as `+    line` (5 characters before `line`: the `+` plus 4 spaces). Models tend to write `+   line` (only 3 spaces) or even `+line` (no spaces). **Always double-check that every `+` line has exactly the same leading whitespace as the original line it replaces or adds next to.** A single missing space causes "Failed to find context" on the *next* hunk - and the error message will blame the wrong line.

4. **The `@@` header is freeform disambiguation text.** It is *not* parsed as a line-number range. It is matched as literal text against the file content to narrow down which occurrence to patch. If the header text doesn't appear in the file, matching falls back to context lines - or fails.

## Matching Algorithm

The tool searches for the *concatenation* of context + removal lines in the file. It needs to find that exact block. If there are multiple matches, the `@@` header helps disambiguate.

## Common Failure Modes

| Symptom | Cause | Fix |
|---|---|---|
| "Failed to find context" | Whitespace mismatch (extra/missing blank lines, tabs vs spaces) | Use `cat -An file \| sed -n 'X,Yp'` to see exact characters including line-endings |
| Patch succeeds but file unchanged | All lines were context (no `+`/`-`) | Add explicit `+` and `-` lines |
| `-` line not being removed | It was treated as a context line because the surrounding context didn't match | Ensure the `-` line's surrounding context lines match exactly |
| `@@` header "not found" | The header text is searched literally in the file content; it's not a label/metadata | Only use text that actually appears in the file, or omit the header entirely |

## Practical Tips

**Diagnose with `cat -An`** - When a patch fails, the error message shows what it *expected*. Compare against `cat -An file.py | sed -n 'X,Yp'` to see the exact whitespace (dollar signs mark EOL, `^I` for tabs).

**Match exactly the right number of blank lines** - A single blank line between two code blocks in your context must be exactly one blank line in the file. Count them with `cat -An`.

**Avoid `@@` headers unless needed** - They add a matching requirement that often fails. Plain context lines (3 before, 3 after) are usually sufficient and more reliable.

**`@@` text must come from the target file** - The tool searches for `@@` header text as a literal string in the file you’re patching. It is *not* a label or qualifier you can invent. Never use `@@` text that doesn’t appear in the file you’re patching.

**For insertions (no removals), use a single `-` + `+` swap** - To insert a line, remove an adjacent line with `-` and re-add it with `+` plus your new lines:
```
 existing_line
+new_line_before
+existing_line  # ← WRONG, this duplicates
```
Instead:
```
- existing_line
+ existing_line
+ new_line_after
```

**For tricky multi-point edits in one file, use multiple hunks** - Each `@@` starts a new hunk. They apply sequentially. Make sure earlier hunks don't shift line numbers that break later hunks' context.

## Anti-Patterns to Avoid

* **Don't use `-` lines as context.** They delete. Use space-prefixed lines for unchanged context.
* **Don't guess at indentation.** Always `cat -An` the actual file first.
* **Don't chain multiple `@@` headers hoping they act as nested qualifiers.** They're just additional literal-text matches that all must succeed.
* **Don't try to patch with only context and no `+`/`-` lines.** It's a no-op that silently "succeeds."
* **It is much preferred to use `apply_patch` directly** rather than writing Python scripts to patch files.
* **It is much preferred to use the `apply_patch` tool for all file modifications**, reserving `sed` for viewing file regions only.

## Workflow for Tricky Patches

1. `sed -n 'X,Yp' file` - see the target region
2. `cat -An file | sed -n 'X,Yp'` - see exact whitespace if step 1's patch fails
3. Write the patch with minimal context (3 lines before/after the change)
4. Verify with `rg` or `sed` after application
