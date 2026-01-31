"""Web search service using Tavily."""

import asyncio
from typing import Dict, List, Any, Optional

from tavily import TavilyClient

from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class WebSearchService:
    """Service to handle web searches."""

    def __init__(self):
        """Initialize the web search service."""
        try:
            self.client = TavilyClient(api_key=settings.TAVILY_API_KEY)
            self.enabled = True
        except Exception as e:
            logger.warning(
                f"Failed to initialize Tavily client: {e}. Web search will be disabled."
            )
            self.client = None
            self.enabled = False

    async def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform a web search.

        Args:
            query: The search query.

        Returns:
            List of search results (title, content, url).
        """
        if not self.enabled or not self.client:
            logger.warning("Web search is disabled or not initialized.")
            return []

        try:
            logger.info(f"Performing web search for query: {query}")
            # Run the blocking Tavily search in a separate thread
            response = await asyncio.to_thread(
                self.client.search, query=query, search_depth="advanced"
            )

            results = []
            for result in response.get("results", []):
                results.append(
                    {
                        "title": result.get("title"),
                        "content": result.get("content"),
                        "url": result.get("url"),
                        "score": result.get("score"),
                    }
                )

            logger.info(f"Found {len(results)} web search results")
            return results

        except Exception as e:
            logger.error(f"Error performing web search: {e}", exc_info=True)
            return []

    def format_results(self, results: List[Dict[str, Any]]) -> str:
        """
        Format search results for the system prompt.

        Args:
            results: List of search result dictionaries.

        Returns:
            Formatted string representation of search results.
        """
        if not results:
            return "No web search results found."

        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.append(
                f"{i}. [Source: {result.get('title', 'No Title')}]({result.get('url', '#')})\n"
                f"   {result.get('content', 'No content available.')}\n"
            )

        return "\n".join(formatted_results)


# Global instance
web_search_service = WebSearchService()
