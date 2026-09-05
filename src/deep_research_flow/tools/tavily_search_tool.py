import os
from datetime import date as date_cls
from typing import Type

from crewai import LLM
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from tavily import TavilyClient

SUMMARIZE_WEBPAGE_PROMPT = """You are tasked with summarizing the raw content of a webpage retrieved from a web search. Your goal is to create a summary that preserves the most important information from the original web page. This summary will be used by a downstream research agent, so it's crucial to maintain the key details without losing essential information.

Here is the raw content of the webpage:

<webpage_content>
{webpage_content}
</webpage_content>

Please follow these guidelines to create your summary:

1. Identify and preserve the main topic or purpose of the webpage.
2. Retain key facts, statistics, and data points that are central to the content's message.
3. Keep important quotes from credible sources or experts.
4. Maintain the chronological order of events if the content is time-sensitive or historical.
5. Preserve any lists or step-by-step instructions if present.
6. Include relevant dates, names, and locations that are crucial to understanding the content.
7. Summarize lengthy explanations while keeping the core message intact.

When handling different types of content:

- For news articles: Focus on the who, what, when, where, why, and how.
- For scientific content: Preserve methodology, results, and conclusions.
- For opinion pieces: Maintain the main arguments and supporting points.
- For product pages: Keep key features, specifications, and unique selling points.

Your summary should be significantly shorter than the original content but comprehensive enough to stand alone as a source of information. Aim for about 25-30 percent of the original length, unless the content is already concise.

Present your summary in the following format:

```
{{
   "summary": "Your summary here, structured with appropriate paragraphs or bullet points as needed",
   "key_excerpts": "First important quote or excerpt, Second important quote or excerpt, Third important quote or excerpt, ...Add more excerpts as needed, up to a maximum of 5"
}}
```

Here are two examples of good summaries:

Example 1 (for a news article):
```json
{{
   "summary": "On July 15, 2023, NASA successfully launched the Artemis II mission from Kennedy Space Center. This marks the first crewed mission to the Moon since Apollo 17 in 1972. The four-person crew, led by Commander Jane Smith, will orbit the Moon for 10 days before returning to Earth. This mission is a crucial step in NASA's plans to establish a permanent human presence on the Moon by 2030.",
   "key_excerpts": "Artemis II represents a new era in space exploration, said NASA Administrator John Doe. The mission will test critical systems for future long-duration stays on the Moon, explained Lead Engineer Sarah Johnson. We're not just going back to the Moon, we're going forward to the Moon, Commander Jane Smith stated during the pre-launch press conference."
}}
```

Example 2 (for a scientific article):
```json
{{
   "summary": "A new study published in Nature Climate Change reveals that global sea levels are rising faster than previously thought. Researchers analyzed satellite data from 1993 to 2022 and found that the rate of sea-level rise has accelerated by 0.08 mm/year² over the past three decades. This acceleration is primarily attributed to melting ice sheets in Greenland and Antarctica. The study projects that if current trends continue, global sea levels could rise by up to 2 meters by 2100, posing significant risks to coastal communities worldwide.",
   "key_excerpts": "Our findings indicate a clear acceleration in sea-level rise, which has significant implications for coastal planning and adaptation strategies, lead author Dr. Emily Brown stated. The rate of ice sheet melt in Greenland and Antarctica has tripled since the 1990s, the study reports. Without immediate and substantial reductions in greenhouse gas emissions, we are looking at potentially catastrophic sea-level rise by the end of this century, warned co-author Professor Michael Green."
}}
```

Remember, your goal is to create a summary that can be easily understood and utilized by a downstream research agent while preserving th most critical information from the original webpage.

Today's date is {date}.
"""


COMPRESS_RESEARCH_SYSTEM_PROMPT = """You are a research assistant that has conducted research on a topic by calling several tools and web searches. Your job is now to clean up the findings, but preserve all of the relevant statements and information that the researcher has gathered. For context, today's date is {date}.

<Task>
You need to clean up information gathered from tool calls and web searches in the existing messages.
All relevant information should be repeated and rewritten verbatim, but in a cleaner format.
The purpose of this step is just to remove any obviously irrelevant or duplicate information.
For example, if three sources all say "X", you could say "These three sources all stated X".
Only these fully comprehensive cleaned findings are going to be returned to the user, so it's crucial that you don't lose any information from the raw messages.
</Task>

<Tool Call Filtering>
**IMPORTANT**: When processing the research messages, focus only on substantive research content:
- **Include**: All tavily_search results and findings from web searches
- **Exclude**: think_tool calls and responses - these are internal agent reflections for decision-making and should not be included in the final research report
- **Focus on**: Actual information gathered from external sources, not the agent's internal reasoning process

The think_tool calls contain strategic reflections and decision-making notes that are internal to the research process but do not contain factual information that should be preserved in the final report.
</Tool Call Filtering>

<Guidelines>
1. Your output findings should be fully comprehensive and include ALL of the information and sources that the researcher has gathered from tool calls and web searches. It is expected that you repeat key information verbatim.
2. This report can be as long as necessary to return ALL of the information that the researcher has gathered.
3. In your report, you should return inline citations for each source that the researcher found. Citations must be placed at the sentence/claim level, immediately after the specific statement they support — never a single citation dropped once at the end of an entire paragraph or source block.
4. You should include a "Sources" section at the end of the report that lists all of the sources the researcher found with corresponding citations, cited against statements in the report.
5. Make sure to include ALL of the sources that the researcher gathered in the report, and how they were used to answer the question!
6. It's really important not to lose any sources. A later LLM will be used to merge this report with others, so having all of the sources is critical.
</Guidelines>

<Output Format>
The report should be structured like this:
**List of Queries and Tool Calls Made**
**Fully Comprehensive Findings**
**List of All Relevant Sources (with citations in the report)**
</Output Format>

<Citation Rules>
- Assign each unique URL a single citation number, and reuse that same number every time you cite it
- IMPORTANT: Cite at the sentence/claim level. Every sentence or discrete fact drawn from a source must end with that source's citation number — do NOT cite a source only once at the end of a paragraph or block that contains multiple sentences from it. If five consecutive sentences all come from source [2], all five sentences end in [2], not just the last one.
- When a single sentence combines facts from more than one source, cite all of them, e.g. "...as shown by two independent studies [1][3]."
- End with ### Sources that lists each source with corresponding numbers
- IMPORTANT: Number sources sequentially without gaps (1,2,3,4...) in the final list regardless of which sources you choose
- Example format:
  Global sea levels are rising faster than previously thought [1]. The rate has accelerated by 0.08 mm/year² over three decades [1]. A separate study reached a similar conclusion using satellite gravimetry [2].

  ### Sources
  [1] Source Title: URL
  [2] Source Title: URL
</Citation Rules>

Critical Reminder: It is extremely important that any information that is even remotely relevant to the user's research topic is preserved verbatim (e.g. don't rewrite it, don't summarize it, don't paraphrase it).
"""

COMPRESS_RESEARCH_TASK_PROMPT = """All above messages are about research conducted by an AI Researcher for the following research topic:

RESEARCH TOPIC: {research_topic}

Your task is to clean up these research findings while preserving ALL information that is relevant to answering this specific research question.

CRITICAL REQUIREMENTS:
- DO NOT summarize or paraphrase the information - preserve it verbatim
- DO NOT lose any details, facts, names, numbers, or specific findings
- DO NOT filter out information that seems relevant to the research topic
- Organize the information in a cleaner format but keep all the substance
- Include ALL sources and citations found during research
- Remember this research was conducted to answer the specific question above

The cleaned findings will be used for final report generation, so comprehensiveness is critical."""


class WebpageSummary(BaseModel):
    summary: str
    key_excerpts: str


class TavilySearchInput(BaseModel):
    """Input schema for the Tavily search tool."""

    query: str = Field(..., description="The search query to run")


class TavilySearchTool(BaseTool):
    """Tavily web search whose results are deduplicated, summarized, and compressed.

    Each result's raw content is condensed by a cheap summarization LLM, then
    the full set of per-result summaries is compressed into a single
    comprehensive, citation-preserving report by a second LLM pass before
    being handed back to the calling agent — so the agent's context only ever
    sees one clean, deduplicated block of findings rather than raw page dumps
    or repetitive per-source summaries.
    """

    name: str = "tavily_search"
    description: str = (
        "Search the web for the given query. Results are deduplicated by URL, "
        "each result's content is summarized, and the summaries are then "
        "compressed into a single comprehensive, source-cited findings report "
        "before being returned, so the output is compact and ready to reason over."
    )
    args_schema: Type[BaseModel] = TavilySearchInput

    max_results: int = 5
    summarizer_llm: str = "openai/gpt-4.1-mini"
    compressor_llm: str = "openai/gpt-4.1"

    def _run(self, query: str) -> str:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return "Error: TAVILY_API_KEY is not set, cannot perform web search."

        client = TavilyClient(api_key=api_key)
        try:
            response = client.search(
                query=query,
                max_results=self.max_results,
                include_raw_content=True,
            )
        except Exception as e:
            return f"Error running Tavily search for '{query}': {e}"

        deduped = []
        seen_urls = set()
        for result in response.get("results", []):
            url = result.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            deduped.append(result)

        if not deduped:
            return f"No results found for query: {query}"

        summarizer = LLM(model=self.summarizer_llm)
        today = date_cls.today().isoformat()

        blocks = []
        for result in deduped:
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            content = result.get("raw_content") or result.get("content") or ""

            if not content:
                blocks.append(f"### {title}\nURL: {url}\n(No content available to summarize.)")
                continue

            try:
                parsed: WebpageSummary = summarizer.call(
                    messages=[
                        {
                            "role": "user",
                            "content": SUMMARIZE_WEBPAGE_PROMPT.format(
                                webpage_content=content, date=today
                            ),
                        }
                    ],
                    response_model=WebpageSummary,
                )
                summary_text = parsed.summary
                excerpts_text = parsed.key_excerpts
            except Exception as e:
                summary_text = content[:1000]
                excerpts_text = f"(Summarization failed: {e})"

            blocks.append(
                f"### {title}\nURL: {url}\nSummary: {summary_text}\nKey Excerpts: {excerpts_text}"
            )

        combined_findings = f"Search results for '{query}':\n\n" + "\n\n".join(blocks)

        compressor = LLM(model=self.compressor_llm)
        try:
            compressed = compressor.call(
                messages=[
                    {
                        "role": "system",
                        "content": COMPRESS_RESEARCH_SYSTEM_PROMPT.format(date=today),
                    },
                    {"role": "user", "content": combined_findings},
                    {
                        "role": "user",
                        "content": COMPRESS_RESEARCH_TASK_PROMPT.format(research_topic=query),
                    },
                ]
            )
            return compressed
        except Exception as e:
            return (
                f"Note: compression step failed ({e}); returning uncompressed "
                f"summarized results below.\n\n{combined_findings}"
            )
