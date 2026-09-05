from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.mcp import MCPServerStdio
from crewai.project import CrewBase, agent, crew, task

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

    @agent
    def researcher_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["researcher_agent"],  # type: ignore[index]
            tools=[
                TavilySearchTool(),
                think_tool,
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
    def conduct_research_task(self) -> Task:
        return Task(
            config=self.tasks_config["conduct_research_task"],  # type: ignore[index]
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
