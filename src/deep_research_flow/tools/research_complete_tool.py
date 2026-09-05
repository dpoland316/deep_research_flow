from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel


class ResearchCompleteInput(BaseModel):
    """Tool for indicating that the research process is complete."""

    pass


class ResearchCompleteTool(BaseTool):
    """Tool for indicating that the research process is complete."""

    name: str = "ResearchComplete"
    description: str = "Tool for indicating that the research process is complete."
    args_schema: Type[BaseModel] = ResearchCompleteInput

    def _run(self) -> str:
        return (
            "Research marked complete. Do not call any more tools — consolidate "
            "all of the ConductResearch findings gathered so far into the final "
            "report now."
        )
