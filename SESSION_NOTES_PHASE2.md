# Deep Research Agent — Phase 2: Research & Report Writing

Session notes for the second phase of `deep_research_flow`: taking phase 1's
confirmed research brief and actually researching it, then writing a saved
report. Picks up where `SESSION_NOTES_PHASE1.md` left off.

## New tool: `think_tool`

`src/deep_research_flow/tools/think_tool.py` — a `@tool`-decorated no-op
reflection tool (`reflection: str` in, a confirmation string echoing it back
out). Its only purpose is to force a deliberate "pause and assess" step into
the agent's tool-calling transcript between searches — the docstring (used
verbatim as the tool description) tells the agent to call it after every
search to weigh what it found, what's missing, and whether to keep going.
Replaced the unused scaffold placeholder `tools/custom_tool.py`, which
nothing referenced.

## New crew: `research_crew`

Two agents, two sequential tasks, in `src/deep_research_flow/crews/research_crew/`.

### `researcher_agent` + `conduct_research_task`

- **Agent** (`config/agents.yaml`): "Deep Research Specialist",
  `llm: anthropic/claude-sonnet-4-6` (verified live — resolves and responds;
  required adding the `anthropic` extra to `crewai[tools,anthropic]` in
  `pyproject.toml` for the native provider). `max_iter: 15`.
- **Task** (`config/tasks.yaml`): description is your provided template
  almost verbatim — read the brief, search broadly then narrow, reflect with
  `think_tool` after every search, stop once confident or after hitting the
  stated tool-call budget (2-3 searches for simple queries, up to 5 for
  complex ones). `expected_output` requires sourced findings plus an explicit
  note of anything unresolved.
- **Tools**: a custom `TavilySearchTool` (see below) and `think_tool`.

Verified live end-to-end (before the search tool was rewritten): the agent
correctly alternated `tavily_search` → `think_tool` → `tavily_search` →
`think_tool`, then stopped and produced a sourced findings report. One
observation: it made 6 searches against its own stated "5 max for complex
queries" — the budget is a prose instruction, not code-enforced, so the model
can drift past it (same distinction as `output_pydantic` schemas being
enforced vs. plain prompt instructions).

### `report_writer_agent` + `write_report_task` (added later)

- **Agent**: "Research Report Writer", same LLM, `max_iter: 8`. Has no search
  tools — only a filesystem MCP server, since its job and tool surface are
  genuinely different from the researcher's (least-privilege: only this agent
  can write files).
- **Task**: takes the prior task's findings (auto-passed via sequential
  process) plus the research brief, compiles a markdown report, invents its
  own short filename title (2-3 words, lowercase, underscore-separated, no
  generic words like "report"), then uses the filesystem MCP tool to write it
  to `output/<title>_{timestamp}.md`. The `{timestamp}` is computed in code
  (`main.py`, `datetime.now().strftime("%Y%m%d_%H%M%S")`) and passed in as a
  kickoff input — same pattern as `{date}` — so the agent can't fabricate the
  wall-clock time, only the title.
- **MCP wiring** (`research_crew.py`): `MCPServerStdio` running
  `npx -y @modelcontextprotocol/server-filesystem <output dir>`, scoped to a
  project-local `output/` directory (`PROJECT_ROOT / "output"`, created via
  `mkdir(parents=True, exist_ok=True)`), which was also added to `.gitignore`.
  First invocation downloads that npm package on demand (needs internet,
  a few extra seconds).

## Custom `TavilySearchTool` (dedup + summarize)

`src/deep_research_flow/tools/tavily_search_tool.py` replaced the built-in
`crewai_tools.TavilySearchTool`. For every query it:

1. Calls Tavily directly via `tavily.TavilyClient` (`include_raw_content=True`).
2. Deduplicates results by `url`.
3. Summarizes each result's content with a separate `LLM(model="openai/gpt-4.1-mini")`
   call, using your summarization template verbatim (`{webpage_content}`/`{date}`
   interpolated), with the `{summary, key_excerpts}` shape enforced via a
   `WebpageSummary` Pydantic model rather than trusting the template's
   prose-only JSON instruction.
4. Returns one formatted block per result (title, URL, summary, key excerpts)
   as the tool's string output, which is what the researcher agent actually
   sees — never raw page dumps.

**Bug found and fixed:** the first version passed `response_format=WebpageSummary`
to `LLM.call()`. That kwarg doesn't exist on the installed `crewai` (1.15.19)
— the correct parameter is `response_model`. The wrong name raised a
`TypeError` on every call, silently caught by the tool's own `except
Exception` fallback, so summarization always fell back to truncated raw
content without any visible error. Fixed by using `response_model=WebpageSummary`
(confirmed correct via `inspect.signature(LLM.call)` and the source comment
noting litellm/instructor returns a Pydantic instance directly for that
param). Note for later: the `getting-started` skill's docs describe this
parameter as `response_format`, which is stale against this installed version.

Added `tavily-python` as an explicit dependency (needed by `TavilySearchTool`)
alongside the `anthropic` extra.

## Flow wiring (`main.py`)

`ScopingFlow` gained a third step after phase 1's `present_scope`:

```python
@listen(present_scope)
def conduct_research(self):
    result = ResearchCrew().crew().kickoff(
        inputs={
            "research_brief": self.state.research_brief,
            "date": date.today().isoformat(),
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        }
    )
    self.state.research_findings = result.raw
```

`ResearchScopeState` gained a `research_findings: str` field. One `crewai run`
/ `kickoff()` now runs all three phases: scope → brief → research + saved
report.

## Operational notes from this session

- **`crewai run` needs a real TTY.** A live run through this session's `!`
  passthrough failed with `EOFError` on the first `input()` call — that
  passthrough has no interactive stdin attached (same reason every test in
  this session used `printf ... | uv run ...`). Not a code bug: `crewai run`'s
  CLI internals (`crewai_cli/run_crew.py`) just `subprocess.run(["uv", "run",
  "kickoff"])` inheriting whatever stdin the parent had. Run it from a real
  terminal window instead.
- **Testing cadence going forward:** wiring/construction checks (imports,
  `crew.agents`/`crew.tasks` shape, tool lists, prompt interpolation) are done
  freely and statically after each edit; live model/tool invocations are held
  until the user confirms they're done making changes for a round, so real
  API calls get batched rather than fired after every small edit.
- **Accidental secret exposure (self-flagged):** while sanity-checking LLM/tool
  wiring earlier in this work, a couple of debug commands printed a Pydantic
  object repr and read `.env` directly, both of which echoed real API keys
  into this session's tool output in plaintext. Nothing left the session, but
  worth remembering: inspect `.env`/secret-bearing objects via redacted
  commands (e.g. `sed 's/=.*/=<redacted>/'`), never raw prints or direct reads.

## How to run

```bash
cd deep_research_flow
crewai run   # from a real terminal, not a non-interactive passthrough
# or: uv run python -m deep_research_flow.main
```

## Next steps

- Live-verify the fixed summarizer and the MCP report-writing step end to end
  (search → summarize → findings → saved `output/<title>_<timestamp>.md`).
- Consider whether the researcher's search-budget "hard limit" needs actual
  code enforcement (e.g. a call counter) if prompt-only adherence proves too
  loose in practice.
- Root `CLAUDE.md` still describes the repo as two independent projects —
  still worth updating to mention `deep_research_flow` as a third.
