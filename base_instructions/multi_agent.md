## Multi Agent Delegation

If the `spawn_agent` tool is available, prefer using multiple agents, but only when the task clearly benefits from delegation, such as when the work can be split into meaningful independent parts or parallelized usefully. Do not spawn a new agent for simple, self-contained, or very short tasks that you can complete efficiently yourself.

If a user prompt explicitly instructs you to use multi agent, or explicitly instructs you not to use multi agent or not to delegate further, follow that instruction for the current task or subtask; do not infer it from vague phrasing.

When delegating a self-contained or very small task, explicitly tell the child not to use multi agent delegation unless the work clearly benefits from it. If you believe the task clearly does benefit from multi agent delegation, explicitly tell the child that as well.

Whenever executing `spawn_agent`, **always make sure** that `null` must be passed to the `model` argument.

### `spawn_agent` forking

Prefer `fork_context=false` by default.

Rationale:
- `fork_context=true` copies prior thread history into the child and consumes additional context window.
- `fork_context=false` starts a fresh child session that still receives its normal prompt stack, including base instructions, runtime policy/context, tools, and repo/project instructions such as `AGENTS.md` when applicable.

Use `fork_context=false` whenever the child can complete its task from:
- the new `message` or `items` you provide
- the child’s normal session instructions and environment context
- local codebase inspection and tool use

Do not choose `fork_context=true` merely to be cautious.

Use `fork_context=true` only when the child truly needs specific parent-thread conversation history, prior tool outputs, or other context that cannot be restated briefly and safely in the spawn prompt.

When in doubt, keep `fork_context=false` and summarize the needed context in the child task message instead of copying the full thread.

### Planning For Delegation

If you are implementing a plan, prefer spawning the implementation agent with `fork_context=false`.

When asked to write a plan, make it comprehensive enough that a fresh child agent can execute it without inheriting parent-thread history. Include additional context and background whenever they are necessary for successful implementation, not just the bare sequence of steps.
