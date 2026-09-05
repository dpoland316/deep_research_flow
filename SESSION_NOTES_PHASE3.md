# Deep Research Agent — Phase 3: Result Compression & Lead Researcher Delegation

Session notes for the third phase of `deep_research_flow`, picking up where
`SESSION_NOTES_PHASE2.md` left off. Two substantive features landed this
phase — a compression pass on Tavily results, and a lead-researcher
delegation pattern that replaces the single researcher agent with a
coordinator that fans work out to sub-agents — plus some repo housekeeping.

## Repo housekeeping (before the feature work)

- Initialized a dedicated git repo for `deep_research_flow` (the nested
  `.git` `crewai create flow` sets up automatically) and pushed it to a new
  private GitHub repo, `dpoland316/deep_research_flow`.
- Rewrote the repo-local git identity from a personal name/work email to
  `dpoland316 <44174946+dpoland316@users.noreply.github.com>` (GitHub's
  private noreply address for the account) and rewrote the existing commit's
  author/committer to match, then force-pushed — repo-local only, doesn't
  touch global git config or the other projects in this sandbox.
- Renamed the flow step `present_scope` → `create_research_brief` in
  `main.py` (clearer name for what the step actually produces) and updated
  both `SESSION_NOTES_PHASE1.md` and `SESSION_NOTES_PHASE2.md` to match.
- Renamed all `anthropic/claude-sonnet-4-6` references to
  `anthropic/claude-sonnet-5` across `research_crew/config/agents.yaml`
  (`researcher_agent`, `lead_researcher_agent`, `report_writer_agent`).
  Left the historical mention in `SESSION_NOTES_PHASE2.md` alone since it
  documents what was actually verified live at that point in time.

## Feature 1: Result compression in `TavilySearchTool`

Added a third stage to the tool's pipeline. It was: search → dedupe by URL →
summarize each result (`openai/gpt-4.1-mini`). Now: search → dedupe →
summarize → **compress**.

The compression step takes every deduped result's summary+excerpts for a
single query and runs them through one more LLM call
(`openai/gpt-4.1`, per your choice) using two prompt templates you provided
verbatim:

- `COMPRESS_RESEARCH_SYSTEM_PROMPT` — instructs the model to clean up and
  merge findings while preserving everything verbatim, explicitly excluding
  `think_tool` reflections from consideration (not relevant here since this
  tool only ever sees `tavily_search` output, but kept as-is since it was
  your exact template), and to produce a
  `**List of Queries and Tool Calls Made**` /
  `**Fully Comprehensive Findings**` / `**List of All Relevant Sources**`
  structured report with sequentially numbered citations.
- `COMPRESS_RESEARCH_TASK_PROMPT` — the per-call instruction, interpolating
  `{research_topic}` (the tool's `query` argument), framed as "all above
  messages are about research conducted for this topic."

Message order for the compressor call mirrors the "all above messages"
framing: system prompt → user message with the raw combined findings → user
message with the task prompt.

**Tested live** against a 3-source dark-matter test payload you supplied
(bypassing Tavily/summarization, feeding pre-summarized blocks straight into
the compression call). First run succeeded structurally but citations landed
once per source block rather than per claim. You asked for tighter citation
enforcement; I strengthened the `<Guidelines>` and `<Citation Rules>`
sections with an explicit "cite at the sentence/claim level, never once at
the end of a paragraph" rule plus a worked example, and re-ran the same test
— the second run cited nearly every individual sentence/quote, confirming
the fix.

Failure handling: if the compression call raises, the tool falls back to the
uncompressed summarized blocks with a visible `Note: compression step
failed...` prefix (not a silent swallow, learned from the Phase 2
`response_format`/`response_model` bug).

## Feature 2: Lead researcher / delegation pattern

The core ask: instead of one `researcher_agent` doing all the searching,
add a `lead_researcher_agent` that decides what needs investigating,
delegates focused sub-topics to sub-agents (in parallel when independent),
and consolidates their findings into one report — implemented via two new
tools, `ConductResearch` and `ResearchComplete`, with your exact tool
descriptions/schemas.

### Key discovery: crewai already supports parallel native tool calls

Before implementing, I checked whether crewai's agent executor could even
support "call ConductResearch multiple times in one turn and run them
concurrently." Initially found a docstring in `crew_agent_executor.py`
suggesting only the first tool call in a batch is processed — but reading
the actual `_handle_native_tool_calls` implementation showed that's stale:
when the LLM returns multiple native tool calls in one turn, crewai runs
them **concurrently in a `ThreadPoolExecutor`** (up to 8 workers) and waits
for all of them before continuing the loop — exactly the
"invoke-asynchronously-then-wait" behavior you asked for, already built in.
(It falls back to sequential-only handling if any tool in the batch has
`result_as_answer` or `max_usage_count` set, which ours don't.)

This meant no custom asyncio orchestration was needed — the parallelism
comes for free from crewai's executor as long as the LLM actually chooses to
emit multiple `ConductResearch` calls in one turn.

### Thread-safety constraint this discovery created

`Agent.execute_task()` mutates a shared, non-thread-safe `agent_executor`
object stored on the `Agent` instance (`self.agent_executor.task = task`,
accumulated `messages`, etc.). If two parallel `ConductResearch` calls
delegated to the *same* `researcher_agent` object, they'd corrupt each
other's execution state. Fix: `ConductResearchTool` takes a
`researcher_agent_factory: Callable[[], Agent]` and builds a **fresh**
`Agent` instance per call rather than reusing one shared instance —
confirmed via `crewai`'s own built-in delegation tool
(`tools/agent_tools/delegate_work_tool.py`), which uses the identical
`Task(..., agent=selected_agent)` + `agent.execute_task(task)` pattern I
followed, just with a factory instead of a fixed list of agents.

### New tools

- **`tools/conduct_research_tool.py`** — `ConductResearchTool`. Field:
  `research_topic: str` (your exact description, "at least a paragraph").
  `_run()` builds a fresh sub-agent via the factory, builds a one-off `Task`
  from `conduct_research_task`'s YAML description/expected_output
  (reparameterized from `{research_brief}` to `{research_topic}`), and
  returns `agent.execute_task(task)`.
- **`tools/research_complete_tool.py`** — `ResearchCompleteTool`. No
  arguments (matches your spec). Returns a short instruction nudging the
  agent to stop calling tools and consolidate — doesn't set
  `result_as_answer`, so the lead's very next plain-text turn becomes the
  final consolidated report rather than a canned message.

### Agent/task/crew restructuring

- **`agents.yaml`**: added `lead_researcher_agent` ("Lead Research
  Coordinator", `anthropic/claude-sonnet-5`, `max_iter: 20`).
- **`tasks.yaml`**: `conduct_research_task` is no longer a top-level Crew
  task — it's now purely a template `ConductResearchTool` reads and
  formats per delegated topic. Added `lead_research_task`, assigned to
  `lead_researcher_agent`.
- **`research_crew.py`**: `researcher_agent` is no longer a top-level
  `@agent`/Crew member — it's built ad hoc via `_build_researcher_agent()`.
  Crew agents are now just `lead_researcher_agent` and `report_writer_agent`;
  tasks are `lead_research_task` → `write_report_task` (sequential, so the
  report writer still auto-receives the lead's consolidated output as
  context — no change needed there). `main.py` needed no changes for this
  part.

### Your manual edits, and what I updated to match

You edited `lead_research_task` directly in the IDE twice; each time I
re-read the file and wired the code to match rather than overwriting your
changes:

1. Added a requirement that the lead use `think_tool` before its first
   `ConductResearch` call (to plan delegation) and after each round (to
   assess progress), plus a `{max_concurrent_research_units}` placeholder in
   a new "PARALLEL RESEARCH" instruction. I added `think_tool` to
   `lead_researcher_agent`'s tool list in `research_crew.py` (now
   `[think_tool, ConductResearch, ResearchComplete]`), and added
   `MAX_CONCURRENT_RESEARCH_UNITS = 3` in `main.py`, passed as
   `max_concurrent_research_units` in `conduct_research()`'s kickoff inputs.
2. Reworked the `<Hard Limits>` section (bias toward a single agent unless
   the request clearly parallelizes, stop when confident) and replaced a
   hardcoded "3" with a `{max_researcher_iterations}` placeholder. I added
   `MAX_RESEARCHER_ITERATIONS = 3` in `main.py` and wired it through the same
   way.

Both additions were verified statically only (template `.format()` succeeds
with no leftover placeholders, tool list confirmed) — no live model calls,
per the standing "batch live runs" instruction.

## README rewrite

The old `README.md` was still the unmodified `crewai create flow`
boilerplate (`{{crew_name}}` placeholders, generic "content creation flow"
description). You asked for it after raising that `crewai flow plot` only
shows the Flow's 3-step `@listen` graph with no visibility into crew/agent
internals or the dynamic delegation loop — confirmed that's a hard
limitation (the plot command has no way to introspect Crew/Agent structure,
let alone an LLM-decided fan-out). Rewrote `README.md` with:

- A Mermaid flowchart of the full architecture (Flow → ScopingCrew →
  ResearchCrew → dynamic per-call sub-agent delegation → report writing).
- A Mermaid sequence diagram walking through one concrete run with two
  independent sub-topics researched in parallel.
- Full documentation of the current implementation: the Flow's 3 steps and
  state fields, both crews, all four tools, setup/env vars, how to run
  (including the `crewai run` TTY caveat from Phase 2), and a known
  limitations section (prompt-only budgets, pending live parallel-delegation
  verification, the `CLAUDE.md` update suggestion).

## Operational notes

- Same testing-cadence discipline as Phase 2: all wiring/construction was
  verified statically (imports, tool `args_schema` fields, template
  `.format()` calls, fresh-instance checks) after each edit; the only live
  model call this phase was the explicitly-requested compression test
  (twice — once to establish the baseline, once to confirm the citation
  fix).
- All phase 3 work committed and pushed to
  `dpoland316/deep_research_flow` as commit `7f976be` ("Add Phase 3: lead
  researcher delegation, result compression, and diagrams").

## How to run

```bash
cd deep_research_flow
crewai run   # from a real terminal, not a non-interactive passthrough
# or: uv run python -m deep_research_flow.main
```

## Next steps

- Live-verify the full delegation flow end to end, specifically confirming
  crewai's thread-pool concurrency actually engages when the lead emits
  multiple `ConductResearch` calls in one turn for a brief with genuinely
  independent sub-topics.
- Consider code-enforcing the search/delegation budgets (still prompt-only)
  if drift proves too loose in practice — a pre-existing note from Phase 2
  that still applies.
- Root `CLAUDE.md` still describes the repo as two independent projects —
  still worth updating to mention `deep_research_flow` as a third.
