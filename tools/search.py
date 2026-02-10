"""Search tool — web search via ddgs text()."""

import logging

from ddgs import DDGS

from .registry import BaseTool

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information. Returns text results with titles, URLs and snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "backend": {
                    "type": "string",
                    "description": "Search backend to use. Defaults to 'auto'.",
                    "enum": ["brave", "duckduckgo", "google"],
                    "default": "google",
                },
            },
            "required": ["query"],
        },
    },
}


def _format_text(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['href']}\n   {r['body']}")
    return "\n\n".join(lines)


class SearchTool(BaseTool):
    """Tool for searching the web using ddgs text()."""

    @property
    def name(self) -> str:
        return "search"

    def definitions(self) -> list[dict]:
        return [WEB_SEARCH_TOOL]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        query = arguments.get("query", "").strip()
        if not query:
            return "No query provided."

        if tool_name != "web_search":
            return f"Unknown search tool: {tool_name}"

        backend = arguments.get("backend", "auto")
        try:
            ddgs = DDGS()
            results = ddgs.text(query, max_results=5, backend=backend)
        except Exception as e:
            logger.exception("web_search failed for query '%s'", query)
            return f"Search failed: {e}"

        if not results:
            return "No results found."

        return _format_text(results)

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the web_search tool to find information from the internet.\n"
            "Use it when the user asks about current events or needs up-to-date information.\n"
            "You can optionally specify a backend (brave, duckduckgo, google. default is google )."
        )
