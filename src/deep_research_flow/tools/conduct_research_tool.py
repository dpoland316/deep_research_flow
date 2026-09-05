from datetime import date as date_cls
from typing import Callable, Type

from crewai import Agent, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class ConductResearchInput(BaseModel):
    research_topic: str = Field(
        description="The topic to research. Should be a single topic, and should "
        "be described in high detail (at least a paragraph).",
    )


class ConductResearchTool(BaseTool):
    """Tool for delegating a research task to a specialized sub-agent."""

    name: str = "ConductResearch"
    description: str = "Tool for delegating a research task to a specialized sub-agent."
    args_schema: Type[BaseModel] = ConductResearchInput

    researcher_agent_factory: Callable[[], Agent]
    task_description_template: str
    task_expected_output: str

    def _run(self, research_topic: str) -> str:
        # A fresh Agent is built per call (rather than reusing one shared
        # instance) because crewai's tool executor runs multiple native tool
        # calls from the same LLM turn concurrently in a thread pool, and
        # Agent.execute_task() mutates a shared, non-thread-safe
        # self.agent_executor on the Agent instance. Reusing one instance
        # across parallel ConductResearch calls would corrupt that state.
        agent = self.researcher_agent_factory()
        task = Task(
            description=self.task_description_template.format(
                research_topic=research_topic,
                date=date_cls.today().isoformat(),
            ),
            expected_output=self.task_expected_output,
            agent=agent,
        )
        return agent.execute_task(task)
