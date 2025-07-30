"""
Brave Search API service.

This module provides a service for interacting with the Brave Search API
with proper error handling, retries, and rate limiting.
"""
import time
from typing import List, Dict, Any, Optional
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..core.config import BraveSearchConfig
from ..core.exceptions import (
    BraveSearchAPIError,
    BraveSearchRateLimitError,
    ValidationError,
)
from ..core.logging import get_logger, log_performance
from ..utils.retry import retry_with_backoff, RetryConfig
from ..utils.validation import validate_search_query, validate_url

logger = get_logger(__name__)


class BraveSearchService:
    """Service for interacting with Brave Search API."""
    
    def __init__(self, config: BraveSearchConfig):
        self.config = config
        self._session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create a configured requests session."""
        session = requests.Session()
        
        # Set up retry strategy
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_backoff_base,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
        )
        
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        # Set default headers
        session.headers.update({
            "Accept": "application/json",
            "X-Subscription-Token": self.config.api_key.get_secret_value(),
            "User-Agent": "Dataiku-Agent/1.0",
        })
        
        return session
    
    @retry_with_backoff(
        max_attempts=3,
        retry_exceptions=(requests.RequestException,),
    )
    @log_performance(logger, "brave_search")
    def search(
        self,
        query: str,
        result_count: Optional[int] = None,
        freshness: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Brave for the given query.
        
        Args:
            query: The search query
            result_count: Number of results to return (overrides config)
            freshness: Result freshness filter (e.g., "pw" for past week)
            extra_params: Additional parameters to pass to the API
            
        Returns:
            List of search results
            
        Raises:
            BraveSearchAPIError: If API returns an error
            BraveSearchRateLimitError: If rate limit is exceeded
            ValidationError: If query validation fails
        """
        # Validate and sanitize query
        try:
            sanitized_query = validate_search_query(query)
        except ValidationError as e:
            logger.error("invalid_search_query", query=query, error=str(e))
            raise
        
        # Build parameters
        params = {
            "q": sanitized_query,
            "count": result_count or self.config.result_count,
            "source": "web",
        }
        
        if self.config.include_ai_summary:
            params["ai"] = "true"
        
        if freshness:
            params["freshness"] = freshness
        
        if extra_params:
            params.update(extra_params)
        
        # Log search request
        logger.info(
            "brave_search_request",
            query=sanitized_query,
            params=params,
        )
        
        try:
            response = self._session.get(
                self.config.base_url,
                params=params,
                timeout=self.config.search_timeout,
            )
            
            # Check for rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise BraveSearchRateLimitError(
                    "Brave Search API rate limit exceeded",
                    retry_after=retry_after,
                )
            
            response.raise_for_status()
            
            data = response.json()
            
            # Extract and validate results
            results = self._extract_results(data)
            
            logger.info(
                "brave_search_success",
                query=sanitized_query,
                result_count=len(results),
                has_ai_summary="ai" in data,
            )
            
            return results
            
        except requests.exceptions.Timeout:
            logger.error("brave_search_timeout", query=sanitized_query)
            raise BraveSearchAPIError(
                "Brave Search API request timed out",
                details={"query": sanitized_query, "timeout": self.config.search_timeout}
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(
                "brave_search_error",
                query=sanitized_query,
                error=str(e),
                status_code=getattr(e.response, "status_code", None),
            )
            
            raise BraveSearchAPIError(
                f"Brave Search API error: {str(e)}",
                status_code=getattr(e.response, "status_code", None),
                response_body=getattr(e.response, "text", None),
            )
    
    def _extract_results(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract and validate search results from API response.
        
        Args:
            data: Raw API response data
            
        Returns:
            List of processed search results
        """
        results = []
        
        # Extract web results
        web_results = data.get("web", {}).get("results", [])
        
        for result in web_results[:self.config.result_count]:
            # Validate URL
            url = result.get("url", "")
            if not validate_url(url):
                logger.warning("invalid_search_result_url", url=url)
                continue
            
            processed_result = {
                "title": result.get("title", "").strip(),
                "snippet": result.get("description", "").strip(),
                "url": url,
                "age": result.get("age"),
                "favicon": result.get("favicon"),
                "domain": result.get("meta_url", {}).get("hostname", ""),
            }
            
            # Add extra metadata if available
            if "extra_snippets" in result:
                processed_result["extra_snippets"] = result["extra_snippets"]
            
            results.append(processed_result)
        
        # Add AI summary if available
        if "ai" in data and data["ai"].get("summary"):
            ai_summary = {
                "type": "ai_summary",
                "content": data["ai"]["summary"],
                "sources": data["ai"].get("sources", []),
            }
            results.insert(0, ai_summary)
        
        return results
    
    def search_with_context(
        self,
        query: str,
        context: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search with additional context prepended to the query.
        
        Args:
            query: The main search query
            context: Additional context (e.g., "Dataiku")
            **kwargs: Additional arguments passed to search()
            
        Returns:
            List of search results
        """
        contextualized_query = f"{context} {query}".strip()
        return self.search(contextualized_query, **kwargs)
    
    def get_quota_status(self) -> Dict[str, Any]:
        """
        Get current API quota status.
        
        Returns:
            Dictionary with quota information
            
        Note: This is a placeholder as Brave doesn't provide a quota endpoint.
        """
        # Brave doesn't provide a quota status endpoint
        # This would need to be tracked locally
        return {
            "quota_available": True,
            "message": "Quota tracking not available from API",
        }
    
    def test_connection(self) -> bool:
        """
        Test if the Brave Search API is accessible.
        
        Returns:
            True if API is accessible
            
        Raises:
            BraveSearchAPIError: If connection test fails
        """
        try:
            # Make a minimal search request
            self.search("test", result_count=1)
            return True
        except Exception as e:
            logger.error("brave_search_connection_test_failed", error=str(e))
            raise BraveSearchAPIError(f"Connection test failed: {str(e)}")
    
    def close(self):
        """Close the session and clean up resources."""
        if self._session:
            self._session.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False 