from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.mcp import MCPServerStdio
from crewai.project import CrewBase, agent, crew, task

from deep_research_flow.tools.conduct_research_tool import ConductResearchTool
from deep_research_flow.tools.research_complete_tool import ResearchCompleteTool
from deep_research_flow.tools.tavily_search_tool import TavilySearchTool
from deep_research_flow.tools.think_tool import think_tool

PROJECT_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_DIR = PROJECT_ROOT / "output"


@CrewBase
class ResearchCrew:
    """Deep-dives a confirmed research brief and saves a written report."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def _build_researcher_agent(self) -> Agent:
        """Builds a fresh researcher sub-agent instance.

        Used as the factory ConductResearchTool calls per delegation — a new
        instance per call, never a shared one, since crewai can run multiple
        ConductResearch tool calls concurrently in separate threads and
        Agent.execute_task() mutates non-thread-safe state on the instance.
        """
        return Agent(
            config=self.agents_config["researcher_agent"],  # type: ignore[index]
            tools=[
                TavilySearchTool(),
                think_tool,
            ],
        )

    @agent
    def lead_researcher_agent(self) -> Agent:
        conduct_research_task_config = self.tasks_config["conduct_research_task"]  # type: ignore[index]
        conduct_research_tool = ConductResearchTool(
            researcher_agent_factory=self._build_researcher_agent,
            task_description_template=conduct_research_task_config["description"],
            task_expected_output=conduct_research_task_config["expected_output"],
        )
        return Agent(
            config=self.agents_config["lead_researcher_agent"],  # type: ignore[index]
            tools=[
                think_tool,
                conduct_research_tool,
                ResearchCompleteTool(),
            ],
        )

    @agent
    def report_writer_agent(self) -> Agent:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filesystem_server = MCPServerStdio(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", str(OUTPUT_DIR)],
            cache_tools_list=True,
        )
        return Agent(
            config=self.agents_config["report_writer_agent"],  # type: ignore[index]
            mcps=[filesystem_server],
        )

    @task
    def lead_research_task(self) -> Task:
        return Task(
            config=self.tasks_config["lead_research_task"],  # type: ignore[index]
        )

    @task
    def write_report_task(self) -> Task:
        return Task(
            config=self.tasks_config["write_report_task"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Research Crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
