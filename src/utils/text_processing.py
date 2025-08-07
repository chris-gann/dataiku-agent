"""
Text processing utilities for query sanitization and URL formatting.

Provides unified functions for cleaning user queries and formatting URLs
for Slack display.
"""

import re
from typing import List, Dict, Any

def sanitize_search_query(query: str) -> str:
    """
    Sanitize user query for search API.
    
    Args:
        query: Raw user query
        
    Returns:
        Cleaned query suitable for search
    """
    # Remove line breaks and replace with spaces
    cleaned = re.sub(r'\s*\n\s*', ' ', query)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Remove special characters that can cause API issues
    cleaned = re.sub(r'[*#@$%^&(){}[\]|\\:;"\'<>?/+=~`]', ' ', cleaned)
    
    # If it's an error message, extract the key parts
    if "error" in cleaned.lower() or "not allowed" in cleaned.lower():
        # Extract key error concepts
        error_keywords = []
        if "not allowed" in cleaned.lower():
            error_keywords.append("not allowed")
        if "prediction" in cleaned.lower():
            error_keywords.append("prediction models")
        if "visual machine learning" in cleaned.lower():
            error_keywords.append("visual machine learning")
        if "profile" in cleaned.lower():
            error_keywords.append("user profile permissions")
            
        if error_keywords:
            cleaned = " ".join(error_keywords)
    
    # Truncate if too long (API limits)
    max_length = 100
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rsplit(' ', 1)[0]  # Cut at word boundary
    
    return cleaned.strip()

def format_urls_as_numbered_links(text: str) -> str:
    """
    Replace URLs in text with numbered Slack-formatted hyperlinks.
    
    Args:
        text: The input text containing URLs
        
    Returns:
        Text with URLs replaced by numbered links like [1], [2], etc.
    """
    # Enhanced pattern to match complete URLs (not already in Slack format)
    # This pattern avoids matching URLs that are already in <URL|text> format
    url_pattern = r'(?<!<)https?://[^\s<>"\'`|]+(?:\.[a-zA-Z]{2,}|:[0-9]+)[^\s<>"\'`|]*[^\s<>"\'`|.,!?;)](?!\|)'
    
    # Find all URLs
    urls = re.findall(url_pattern, text)
    
    if not urls:
        return text
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    # Replace each unique URL with a numbered Slack link
    result = text
    for i, url in enumerate(unique_urls, 1):
        # Create Slack-formatted link: <url|[number]>
        slack_link = f"<{url}|[{i}]>"
        # Replace all occurrences of this URL
        result = result.replace(url, slack_link)
    
    return result

def convert_numbered_refs_to_links(text: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Convert numbered references like [1], [2] to proper Slack hyperlinks using search results.
    
    Args:
        text: Text containing numbered references
        search_results: List of search results with URLs
        
    Returns:
        Text with numbered references converted to Slack hyperlinks
    """
    if not search_results:
        return text
    
    # Create mapping of numbers to URLs
    url_map = {}
    for i, result in enumerate(search_results, 1):
        url = result.get('url', '')
        if url:
            url_map[i] = url
    
    # First, temporarily replace any existing Slack links to avoid double-processing
    existing_links = []
    placeholder_pattern = "SLACKLINK_PLACEHOLDER_{}"
    
    def store_existing_link(match):
        index = len(existing_links)
        existing_links.append(match.group(0))
        return placeholder_pattern.format(index)
    
    # Store existing Slack links
    text_with_placeholders = re.sub(r'<[^>]+\|[^>]+>', store_existing_link, text)
    
    # Pattern to find numbered references like [1], [2], etc.
    def replace_numbered_ref(match):
        ref_num = int(match.group(1))
        if ref_num in url_map:
            url = url_map[ref_num]
            return f"<{url}|[{ref_num}]>"
        else:
            # Keep the original reference if no URL found
            return match.group(0)
    
    # Replace numbered references with Slack hyperlinks
    result = re.sub(r'\[(\d+)\]', replace_numbered_ref, text_with_placeholders)
    
    # Restore existing Slack links
    for i, original_link in enumerate(existing_links):
        result = result.replace(placeholder_pattern.format(i), original_link)
    
    return result

def format_response_with_sources(answer: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Format the response with Slack formatting and numbered URL links.
    
    Args:
        answer: The synthesized answer
        search_results: The search results to map numbered references to actual URLs
        
    Returns:
        Slack-formatted answer with numbered URL links
    """
    if not answer:
        return answer
    
    # Fix double asterisks to single asterisks for proper Slack bold formatting
    # Replace **text** with *text* (but not if already single asterisks)
    formatted_answer = re.sub(r'\*\*([^\*]+?)\*\*', r'*\1*', answer)
    
    # Remove any "References:" section at the bottom and everything after it
    # This is more aggressive to catch various formats
    references_split = re.split(r'\n\s*References?\s*:?\s*\n', formatted_answer, flags=re.IGNORECASE)
    if len(references_split) > 1:
        # Take only the content before the References section
        formatted_answer = references_split[0].rstrip()
    
    # Also remove trailing reference patterns that might remain
    formatted_answer = re.sub(r'\n\s*References?\s*:?\s*.*$', '', formatted_answer, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove any lingering malformed link patterns at the end
    formatted_answer = re.sub(r'\n\s*<[^>]*\|[^>]*>\s*<[^>]*\|[^>]*>\s*$', '', formatted_answer)
    formatted_answer = re.sub(r'\n\s*<[^>]*\|[^>]*>\s*\[[^\]]+\]\s*$', '', formatted_answer)
    
    # Convert numbered references to proper Slack hyperlinks using search results
    formatted_answer = convert_numbered_refs_to_links(formatted_answer, search_results)
    
    # Also handle any remaining plain URLs
    formatted_answer = format_urls_as_numbered_links(formatted_answer)
    
    # Clean up any trailing whitespace
    formatted_answer = formatted_answer.rstrip()
    
    return formatted_answer