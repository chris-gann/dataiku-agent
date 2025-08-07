"""
Unified OpenAI AI service for answer synthesis.

Provides consistent OpenAI o4-mini integration for generating responses
from search results.
"""

import time
from typing import List, Dict, Any

from ..core.clients import get_openai_client, get_logger
from ..core.config import SYSTEM_PROMPT, REASONING_EFFORT

logger = get_logger()

def synthesize_answer(query: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Use OpenAI to synthesize an answer from search results.
    
    Args:
        query: The user's question
        search_results: List of search results from Brave
        
    Returns:
        Synthesized answer from OpenAI
    """
    start_time = time.time()
    
    # Build context from search results
    context_parts = []
    for i, result in enumerate(search_results, 1):
        context_parts.append(f"Result {i}:")
        context_parts.append(f"Title: {result['title']}")
        context_parts.append(f"Content: {result['snippet']}")
        context_parts.append(f"URL: {result['url']}")
        context_parts.append("")
    
    context = "\n".join(context_parts)
    
    # Create the user message with context
    user_message = f"""Based on the following search results, please answer this question: {query}

Search Results:
{context}

Please provide a helpful, accurate answer based on these search results. 

IMPORTANT URL INSTRUCTIONS:
- When referencing URLs from the search results, you can use either complete URLs OR numbered references like [1], [2]
- If using numbered references, make sure they correspond to actual URLs from the search results above
- NEVER use partial URLs like "dataiku.com/product/" - always use complete URLs from search results
- Numbered references will be automatically converted to clickable Slack hyperlinks

Format your response using Slack mrkdwn formatting for better readability."""

    try:
        logger.info("calling_openai_o4_mini", model="o4-mini", reasoning_effort=REASONING_EFFORT)
        
        openai_client = get_openai_client()
        
        # Retry logic for OpenAI calls
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = openai_client.chat.completions.create(
                    model="o4-mini",  # Using OpenAI's o4-mini reasoning model
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    max_completion_tokens=1500,  # o4-mini uses max_completion_tokens
                    reasoning_effort=REASONING_EFFORT,  # "low", "medium", or "high"
                    timeout=30  # Add timeout for OpenAI calls
                )
                break  # Success, exit retry loop
            except Exception as retry_error:
                if attempt < max_retries and "rate_limit" in str(retry_error).lower():
                    wait_time = (attempt + 1) * 2  # Exponential backoff
                    logger.warning("openai_rate_limit_retrying", 
                                 attempt=attempt + 1, 
                                 wait_time=wait_time)
                    time.sleep(wait_time)
                    continue
                else:
                    raise retry_error
        
        answer = response.choices[0].message.content
        
        logger.info(
            "openai_synthesis_completed",
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
            tokens_used=response.usage.total_tokens if response.usage else 0,
            answer_preview=answer[:100] if answer else "None"
        )
        
        return answer
        
    except Exception as e:
        logger.error("openai_o4_mini_failed", error=str(e), query=query, error_type=type(e).__name__)
        return None