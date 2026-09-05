# Deep Research Agent — Phase 1: Scoping

Session notes for the first phase of the `deep_research_flow` project: a scoping
agent that turns a raw, possibly-vague request into a detailed research brief
before any actual research happens.

## Project setup

Scaffolded with `crewai create flow deep_research_flow --classic --skip-provider`
(classic YAML structure, not the JSON-first `.jsonc` format used by `crewai_app`).
The generated `content_crew` sample was renamed to `scoping_crew` and rebuilt from
scratch. `.env` was copied from `latest_ai_flow` (same `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY` / `SERPER_API_KEY`) since each CrewAI project keeps its own.
The unused `run_with_trigger` script/function from the scaffold was removed —
this phase is a plain interactive CLI flow, not a webhook-triggered one.

## Architecture

`ScopingFlow` (`src/deep_research_flow/main.py`) drives one crew,
`ScopingCrew` (`src/deep_research_flow/crews/scoping_crew/`), in a loop until
the scope is confirmed, then hands off a finished research brief.

### `scoping_agent` (`config/agents.yaml`)

A single agent, "Research Scope Analyst" — one agent is enough here since both
tasks share the same persona, tool surface (none), and LLM (`openai/gpt-4o`).

### `assess_scope_task`

Judges the conversation so far against: the specific subject/question, any
timeframe/recency requirement, and the desired depth (overview vs. deep dive).
Outputs a `ScopeAssessment` (`scope_is_clear: bool`, `clarifying_question: str`).

**Clarifying-question behavior:** originally instructed to ask about one
missing dimension at a time. Changed so that when multiple dimensions are
unclear, the agent bundles them into **one** `clarifying_question` string
containing several concrete sub-questions (e.g. "What criteria matter most —
price, quality, atmosphere? Should this cover the whole city or one
neighborhood?"). Goal: resolve everything in a single round-trip with the
user rather than trickling out one question per round. Verified live — a
fully-specified request needs zero clarifying rounds, a vague one gets exactly
one bundled question, and answers that dodge part of the question correctly
still trigger a follow-up.

### `write_research_brief_task`

Runs only after the scope is confirmed clear — wired as a `crewai`
`ConditionalTask` (`condition=_scope_was_confirmed`, checking the previous
task's `ScopeAssessment.scope_is_clear`), so the extra LLM call is skipped
entirely on rounds that still need clarification. Outputs a `ResearchBrief`
(`research_brief: str`).

The task description encodes six rules for turning the conversation into the
brief:
1. Maximize specificity — include every detail the user actually gave.
2. Flag dimensions the domain needs but the user never specified as *open
   considerations* for the researcher, not assumed preferences.
3. Never invent a preference or constraint; say explicitly when something is
   unspecified and should stay flexible.
4. Keep research scope (what to investigate, can be broader) distinct from
   user preferences (must only include what was actually stated).
5. Write it in the first person, as the user.
6. Sourcing guidance: prefer official/primary sites for products and travel,
   original papers/journals for academic topics, LinkedIn/personal sites for
   people, and sources in the request's own language when applicable.

Verified live on two cases: a coffee-shop query needing one clarifying round,
and a fully-specified quantum-computing-startups query needing zero — both
produced detailed first-person briefs with open considerations and sourcing
guidance, matching the rules above.

### Flow loop (`ScopingFlow.define_scope`)

- Captures the initial request via `input()`.
- Loops: kicks off `ScopingCrew` with the running `conversation` transcript.
  - Reads `result.tasks_output[0].pydantic` (the `ScopeAssessment`) and
    `result.tasks_output[1].pydantic` (the `ResearchBrief`, `None` if the
    conditional task was skipped).
  - If `scope_is_clear` (or the round cap is hit — see below), stores
    `brief.research_brief` in state and breaks. Falls back to the raw
    conversation text if the brief somehow didn't generate.
  - Otherwise, prints `clarifying_question`, reads the answer via `input()`,
    appends both to `conversation`, and loops again.
- Capped at `MAX_CLARIFYING_QUESTIONS = 3`. On the final allowed round, a
  `final_round_notice` string is interpolated into `assess_scope_task`'s
  description telling the agent to stop asking and conclude — a safety net so
  the loop can't run forever, backed by `or is_final_round` in the code in
  case the model ever ignores the instruction.
- `create_research_brief` (the next `@listen` step) prints the finished
  `research_brief` — this is the artifact the next phase (actual research)
  will consume.

### A note on `output_pydantic`

`ScopeAssessment`/`ResearchBrief` are set as `output_pydantic=...` in
`scoping_crew.py` (not YAML — a Python class can't be expressed in YAML).
This isn't just a hopeful prompt: since `scoping_agent` has no tools, CrewAI
passes the schema straight through as the LLM provider's native
structured-output constraint, then re-validates the result with Pydantic on
the way out, with an automatic second LLM-call fallback if the first
response doesn't parse. In the rare case even that fails, `.pydantic` comes
back `None` rather than raising — which is why the flow code checks for that
rather than assuming the brief is always present.

## Tracing

Enabled for this project via `crewai traces enable` (confirmed with
`crewai traces status` → Overall Status: ENABLED). Authenticated to CrewAI
AMP via `crewai login`. Runs now finalize a trace batch with a link to
`app.crewai.com` at the end of each `crewai run`.

## How to run

```bash
cd deep_research_flow
crewai run
# or: uv run python -m deep_research_flow.main
```

## Next steps

- Wire `ScopingFlow`'s `research_brief` output into an actual research
  crew/step (search, synthesis, writing) as the next phase of the flow.
- Root `CLAUDE.md` still describes the repo as holding two independent
  projects — worth updating to mention `deep_research_flow` as a third.
