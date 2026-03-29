# About the `apply_patch` command

**CRITICAL REQUIREMENT:** You **MUST ALWAYS** use the `apply_patch` shell command to edit files, no matter what. **NEVER** use raw commands like `sed`, `patch`, `awk`, `echo`, or try to write python scripts to modify files, unless the user explicitly specifies otherwise.

Your patch language is a stripped‑down, file‑oriented diff format designed to be easy to parse and safe to apply. You can think of it as a high‑level envelope:

*** Begin Patch
[ one or more file sections ]
*** End Patch

Within that envelope, you get a sequence of file operations.
You MUST include a header to specify the action you are taking.
Each operation starts with one of three headers:

*** Add File: <path> - create a new file. Every following line is a + line (the initial contents).
*** Delete File: <path> - remove an existing file. Nothing follows.
*** Update File: <path> - patch an existing file in place (optionally with a rename).

May be immediately followed by *** Move to: <new path> if you want to rename the file.
Then one or more "hunks", each introduced by @@ (optionally followed by a hunk header).
Within a hunk each line starts with:

- " " (space) - context line (unchanged line in the file)
- "+" - added line
- "-" - removed line

The @@ header is optional. If you need to disambiguate between multiple occurrences of the same code, you can add context after @@:

```rust
@@ class BaseClass
 line1
 line2
 line3
-old_line
+new_line
 line4
 line5
 line6
```

You can also chain multiple @@ headers for complex contexts:

```rust
@@ class BaseClass
@@     fn method():
 line1
 line2
 line3
-old_line
+new_line
 line4
 line5
 line6
```

The full grammar definition is below:
Patch := Begin { FileOp } End
Begin := "*** Begin Patch" NEWLINE
End := "*** End Patch" NEWLINE
FileOp := AddFile | DeleteFile | UpdateFile
AddFile := "*** Add File: " path NEWLINE { "+" line NEWLINE }
DeleteFile := "*** Delete File: " path NEWLINE
UpdateFile := "*** Update File: " path NEWLINE [ MoveTo ] { Hunk }
MoveTo := "*** Move to: " newPath NEWLINE
Hunk := "@@" [ header ] NEWLINE { HunkLine } [ "*** End of File" NEWLINE ]
HunkLine := (" " | "-" | "+") text NEWLINE

A full patch can combine several operations:

*** Begin Patch
*** Add File: hello.txt
+Hello world
*** Update File: src/app.py
*** Move to: src/main.py
@@ def greet():
-print("Hi")
+print("Hello, world!")
*** Delete File: obsolete.txt
*** End Patch

It is important to remember:

- You must include a header with your intended action (Add/Delete/Update)
- You must prefix new lines with `+` even when creating a new file
- File references can only be relative, NEVER ABSOLUTE.

Invoke the apply_patch command via stdin:

```
shell {"command":["bash","-lc","apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: hello.txt\n+Hello, world!\n*** End Patch\nEOF\n"]}
```
