"""
Unified Brave Search service for Dataiku-related queries.

Provides a single, robust implementation of Brave Search functionality
used by both the main app and LangGraph agent.
"""

import time
import requests
from typing import List, Dict, Any

from ..core.clients import get_logger
from ..core.config import BRAVE_SEARCH_URL, BRAVE_HEADERS
from ..utils.text_processing import sanitize_search_query

logger = get_logger()

def search_brave(query: str, retry_count: int = 0) -> List[Dict[str, Any]]:
    """
    Search Brave for the given query and return top results.
    
    Args:
        query: The search query
        retry_count: Current retry attempt (for internal use)
        
    Returns:
        List of search results with title, snippet, and URL
    """
    start_time = time.time()
    max_retries = 2
    
    try:
        # Sanitize the query before searching
        clean_query = sanitize_search_query(query)
        logger.info("query_sanitized", 
                   original=query[:100], 
                   sanitized=clean_query,
                   retry_count=retry_count)
        
        params = {
            "q": f"{clean_query} Dataiku",  # Add Dataiku to focus results
            "count": 5,  # Reduced from 10 to 5 for faster processing
            "source": "web",
            "ai": "true"
        }
        
        response = requests.get(
            BRAVE_SEARCH_URL,
            headers=BRAVE_HEADERS,
            params=params,
            timeout=8  # Increased timeout for better reliability
        )
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        # Extract web results
        for result in data.get("web", {}).get("results", [])[:5]:
            results.append({
                "title": result.get("title", ""),
                "snippet": result.get("description", ""),
                "url": result.get("url", "")
            })
        
        logger.info(
            "brave_search_completed",
            query=query,
            result_count=len(results),
            duration_ms=int((time.time() - start_time) * 1000)
        )
        
        return results
        
    except requests.exceptions.RequestException as e:
        logger.error("brave_search_failed", 
                    error=str(e), 
                    query=query, 
                    retry_count=retry_count,
                    error_type=type(e).__name__)
        
        # Retry logic for transient errors
        if retry_count < max_retries and isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            logger.info("retrying_brave_search", retry_count=retry_count + 1)
            time.sleep(1 * (retry_count + 1))  # Exponential backoff
            return search_brave(query, retry_count + 1)
        
        raise

def search_brave_with_metadata(query: str) -> Dict[str, Any]:
    """
    Search Brave and return results with additional metadata.
    Used by LangGraph agent for enhanced functionality.
    
    Args:
        query: The search query to execute
        
    Returns:
        Dictionary containing search results and metadata
    """
    start_time = time.time()
    
    try:
        results = search_brave(query)
        
        # Add relevance scoring for enhanced results
        enhanced_results = []
        for result in results:
            enhanced_result = result.copy()
            enhanced_result["relevance_score"] = _calculate_relevance_score(result, query)
            enhanced_results.append(enhanced_result)
        
        # Sort by relevance score
        enhanced_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info("brave_search_with_metadata_completed", 
                   query=query,
                   result_count=len(enhanced_results),
                   duration_ms=duration_ms)
        
        return {
            "success": True,
            "results": enhanced_results,
            "query_used": sanitize_search_query(query),
            "duration_ms": duration_ms,
            "total_results": len(enhanced_results)
        }
        
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("brave_search_with_metadata_failed", 
                    error=str(e), 
                    query=query,
                    error_type=type(e).__name__,
                    duration_ms=duration_ms)
        
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "query_used": query,
            "duration_ms": duration_ms
        }

def _calculate_relevance_score(result: Dict[str, Any], query: str) -> float:
    """Calculate relevance score for search results."""
    score = 0.0
    
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    url = result.get("url", "").lower()
    query_lower = query.lower()
    
    # Check for exact query matches
    if query_lower in title:
        score += 3.0
    if query_lower in snippet:
        score += 2.0
    if query_lower in url:
        score += 1.0
    
    # Check for Dataiku domain authority
    if "dataiku.com" in url:
        score += 2.0
    if "doc.dataiku.com" in url:
        score += 3.0
    
    # Check for query word matches
    query_words = query_lower.split()
    for word in query_words:
        if len(word) > 3:  # Skip short words
            if word in title:
                score += 0.5
            if word in snippet:
                score += 0.3
    
    return score