"""Wikipedia tool — search Wikipedia via MediaWiki API."""

import json
import logging
import urllib.parse
import urllib.request

from .registry import BaseTool

logger = logging.getLogger(__name__)

WIKIPEDIA_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "wikipedia_search",
        "description": "Search Wikipedia for encyclopedic knowledge. Returns article titles, URLs and summaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "language": {
                    "type": "string",
                    "description": "Language for Wikipedia search. Defaults to 'en'.",
                    "enum": ["en", "zh"],
                    "default": "en",
                },
            },
            "required": ["query"],
        },
    },
}

_MAX_SUMMARY_LEN = 500


def _api_get(language: str, params: dict) -> dict:
    """Send a GET request to the MediaWiki API and return parsed JSON."""
    base = f"https://{language}.wikipedia.org/w/api.php"
    url = f"{base}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "GemenBot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _search_and_summarize(query: str, language: str) -> str:
    """Search Wikipedia and fetch intro extracts for the top results."""
    # Step 1: search
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "utf8": 1,
        "format": "json",
        "srlimit": 3,
    }
    data = _api_get(language, search_params)
    hits = data.get("query", {}).get("search", [])
    if not hits:
        return "No Wikipedia results found."

    # Step 2: fetch extracts
    page_ids = "|".join(str(h["pageid"]) for h in hits)
    extract_params = {
        "action": "query",
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "pageids": page_ids,
        "format": "json",
    }
    ext_data = _api_get(language, extract_params)
    pages = ext_data.get("query", {}).get("pages", {})

    # Step 3: format
    lines = []
    for i, hit in enumerate(hits, 1):
        pid = str(hit["pageid"])
        title = hit["title"]
        url = f"https://{language}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
        extract = pages.get(pid, {}).get("extract", "")
        if len(extract) > _MAX_SUMMARY_LEN:
            extract = extract[:_MAX_SUMMARY_LEN].rsplit(" ", 1)[0] + "…"
        lines.append(f"{i}. {title}\n   {url}\n   {extract}")

    return "\n\n".join(lines)


class WikipediaTool(BaseTool):
    """Tool for searching Wikipedia via the MediaWiki API."""

    def definitions(self) -> list[dict]:
        return [WIKIPEDIA_SEARCH_TOOL]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name != "wikipedia_search":
            return f"Unknown tool: {tool_name}"

        query = arguments.get("query", "").strip()
        if not query:
            return "No query provided."

        language = arguments.get("language", "en")
        if language not in ("en", "zh"):
            language = "en"

        try:
            return _search_and_summarize(query, language)
        except Exception as e:
            logger.exception("wikipedia_search failed for query '%s'", query)
            return f"Wikipedia search failed: {e}"

    def get_instruction(self) -> str:
        return (
            "\n\nYou have the wikipedia_search tool to look up encyclopedic knowledge on Wikipedia.\n"
            "Use it when the user asks about factual or encyclopedic topics.\n"
            "You can specify language: 'en' (English, default) or 'zh' (Chinese)."
        )
