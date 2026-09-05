from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai.tasks.conditional_task import ConditionalTask
from crewai.tasks.task_output import TaskOutput
from pydantic import BaseModel


class ScopeAssessment(BaseModel):
    scope_is_clear: bool
    clarifying_question: str = ""


class ResearchBrief(BaseModel):
    research_brief: str


def _scope_was_confirmed(previous_output: TaskOutput) -> bool:
    assessment: Any = previous_output.pydantic
    return bool(assessment and assessment.scope_is_clear)


@CrewBase
class ScopingCrew:
    """Assesses whether a research request's scope is well-defined."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def scoping_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["scoping_agent"],  # type: ignore[index]
        )

    @task
    def assess_scope_task(self) -> Task:
        return Task(
            config=self.tasks_config["assess_scope_task"],  # type: ignore[index]
            output_pydantic=ScopeAssessment,
        )

    @task
    def write_research_brief_task(self) -> Task:
        return ConditionalTask(
            config=self.tasks_config["write_research_brief_task"],  # type: ignore[index]
            output_pydantic=ResearchBrief,
            condition=_scope_was_confirmed,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Scoping Crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
