#!/usr/bin/env python
from datetime import date, datetime

from pydantic import BaseModel

from crewai.flow import Flow, listen, start

from deep_research_flow.crews.research_crew.research_crew import ResearchCrew
from deep_research_flow.crews.scoping_crew.scoping_crew import ScopingCrew

MAX_CLARIFYING_QUESTIONS = 3
FINAL_ROUND_NOTICE = (
    "IMPORTANT: This is the final clarification round allowed. Do not ask another "
    "question under any circumstances — mark the scope as clear so the research brief "
    "can be written from what has been provided so far."
)


class ResearchScopeState(BaseModel):
    initial_request: str = ""
    conversation: str = ""
    clarifying_questions_asked: int = 0
    research_brief: str = ""
    research_findings: str = ""


class ScopingFlow(Flow[ResearchScopeState]):
    """Phase 1 of the deep research agent: turn a raw request into a research brief."""

    @start()
    def define_scope(self):
        self.state.initial_request = input(
            "What would you like the research agent to investigate?\n> "
        ).strip()
        self.state.conversation = f"Initial research request: {self.state.initial_request}"

        while True:
            is_final_round = self.state.clarifying_questions_asked >= MAX_CLARIFYING_QUESTIONS
            result = ScopingCrew().crew().kickoff(
                inputs={
                    "conversation": self.state.conversation,
                    "final_round_notice": FINAL_ROUND_NOTICE if is_final_round else "",
                }
            )
            assessment = result.tasks_output[0].pydantic
            brief = result.tasks_output[1].pydantic

            if assessment.scope_is_clear or is_final_round:
                self.state.research_brief = (
                    brief.research_brief if brief else self.state.conversation
                )
                break

            answer = input(f"\n{assessment.clarifying_question}\n> ").strip()
            self.state.conversation += (
                f"\nClarifying question: {assessment.clarifying_question}"
                f"\nUser's answer: {answer}"
            )
            self.state.clarifying_questions_asked += 1

    @listen(define_scope)
    def present_scope(self):
        print("\n=== Research Brief ===")
        print(self.state.research_brief)
        return self.state.research_brief

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

        print("\n=== Research Findings ===")
        print(self.state.research_findings)
        return self.state.research_findings


def kickoff():
    scoping_flow = ScopingFlow()
    scoping_flow.kickoff()


def plot():
    scoping_flow = ScopingFlow()
    scoping_flow.plot()


if __name__ == "__main__":
    kickoff()
