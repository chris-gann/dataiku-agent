#!/usr/bin/env python3
"""
Test script for Dataiku Agent APIs
Tests Brave Search and OpenAI o4-mini integration without Slack
"""

import os
import time
import json
import re
from typing import List, Dict, Any

import requests
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")
O3_REASONING_EFFORT = os.environ.get("O3_REASONING_EFFORT", "medium")

# Brave Search configuration
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_HEADERS = {
    "Accept": "application/json",
    "X-Subscription-Token": BRAVE_API_KEY
}

# System prompt for OpenAI
SYSTEM_PROMPT = """You are a helpful Dataiku expert assistant. You provide accurate, concise answers based on the search results provided.

Format your response using Slack's mrkdwn formatting:
- Use *bold* for important terms and headings (single asterisks, NOT double)
- Use _italic_ for emphasis (underscores)
- Use `code` for technical terms, file names, and UI elements (backticks)
- Use bullet points with • for lists
- Use numbered lists when showing steps (1. 2. 3.)
- Use > for quotes or important notes
- Keep paragraphs short and scannable

CRITICAL FORMATTING RULES:
- For bold text, use *single asterisks* NOT **double asterisks**
- When including URLs, write them as plain URLs (like https://example.com) - do NOT format them as links
- The system will automatically convert URLs to numbered clickable links

Focus on being helpful, clear, and accurate in your responses about Dataiku's features, capabilities, and usage."""

def test_brave_search(query: str) -> List[Dict[str, Any]]:
    """Test Brave Search API"""
    print(f"🔍 Testing Brave Search with query: '{query}'")
    
    if not BRAVE_API_KEY:
        print("❌ BRAVE_API_KEY not found in environment")
        return []
    
    try:
        params = {
            "q": f"{query} Dataiku",
            "count": 10,
            "source": "web",
            "ai": "true"
        }
        
        start_time = time.time()
        response = requests.get(
            BRAVE_SEARCH_URL,
            headers=BRAVE_HEADERS,
            params=params,
            timeout=10
        )
        duration = time.time() - start_time
        
        response.raise_for_status()
        data = response.json()
        
        results = []
        for result in data.get("web", {}).get("results", [])[:10]:
            results.append({
                "title": result.get("title", ""),
                "snippet": result.get("description", ""),
                "url": result.get("url", "")
            })
        
        print(f"✅ Brave Search successful: {len(results)} results in {duration:.2f}s")
        
        # Show first few results
        for i, result in enumerate(results[:3], 1):
            print(f"  {i}. {result['title'][:80]}...")
            print(f"     {result['url']}")
        
        return results
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Brave Search failed: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error in Brave Search: {e}")
        return []

def test_openai_synthesis(query: str, search_results: List[Dict[str, Any]]) -> str:
    """Test OpenAI o4-mini synthesis"""
    print(f"\n🤖 Testing OpenAI o4-mini synthesis...")
    
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not found in environment")
        return ""
    
    if not search_results:
        print("❌ No search results to synthesize")
        return ""
    
    try:
        # Initialize OpenAI client
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Build context from search results
        context_parts = []
        for i, result in enumerate(search_results, 1):
            context_parts.append(f"Result {i}:")
            context_parts.append(f"Title: {result['title']}")
            context_parts.append(f"Content: {result['snippet']}")
            context_parts.append(f"URL: {result['url']}")
            context_parts.append("")
        
        context = "\n".join(context_parts)
        
        user_message = f"""Based on the following search results, please answer this question: {query}

Search Results:
{context}

Please provide a helpful, accurate answer based on these search results. Include relevant URLs from the search results naturally within your response text. Format your response using Slack mrkdwn formatting for better readability."""

        print(f"📝 Using model: o4-mini with reasoning effort: {O3_REASONING_EFFORT}")
        
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            max_completion_tokens=1000,  # o4-mini uses max_completion_tokens like o3
            # o4-mini reasoning effort
            reasoning_effort=O3_REASONING_EFFORT
        )
        duration = time.time() - start_time
        
        answer = response.choices[0].message.content
        tokens_used = response.usage.total_tokens if response.usage else 0
        
        print(f"✅ OpenAI o4-mini successful: {tokens_used} tokens in {duration:.2f}s")
        return answer
        
    except Exception as e:
        print(f"❌ OpenAI o4-mini failed: {e}")
        print(f"   This might be because o4-mini is not available in your OpenAI account yet")
        print(f"   Trying with gpt-4-turbo-preview as fallback...")
        
        # Fallback to GPT-4
        try:
            start_time = time.time()
            response = openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            duration = time.time() - start_time
            
            answer = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            print(f"✅ GPT-4 fallback successful: {tokens_used} tokens in {duration:.2f}s")
            return answer
            
        except Exception as fallback_error:
            print(f"❌ GPT-4 fallback also failed: {fallback_error}")
            return ""

def format_urls_as_numbered_links(text: str) -> str:
    """
    Replace URLs in text with numbered Slack-formatted hyperlinks.
    
    Args:
        text: The input text containing URLs
        
    Returns:
        Text with URLs replaced by numbered links like [1], [2], etc.
    """
    # Pattern to match plain URLs (not already in Slack format)
    # This pattern avoids matching URLs that are already in <URL|text> format
    url_pattern = r'(?<!<)https?://[^\s<>"\'`|]+[^\s<>"\'`|.,!?;)](?!\|)'
    
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


def format_response_with_sources(answer: str, search_results: List[Dict[str, Any]]) -> str:
    """Format the response with Slack formatting and numbered URL links"""
    if not answer:
        return answer
    
    # Fix double asterisks to single asterisks for proper Slack bold formatting
    formatted_answer = re.sub(r'\*\*([^\*]+?)\*\*', r'*\1*', answer)
    
    # Format URLs as numbered links
    formatted_answer = format_urls_as_numbered_links(formatted_answer)
    
    return formatted_answer

def main():
    """Main test function"""
    print("🚀 Testing Dataiku Agent APIs\n")
    
    # Check environment variables
    print("🔑 Checking API keys...")
    if OPENAI_API_KEY:
        print(f"✅ OpenAI API key found (ends with: ...{OPENAI_API_KEY[-8:]})")
    else:
        print("❌ OpenAI API key missing")
    
    if BRAVE_API_KEY:
        print(f"✅ Brave API key found (ends with: ...{BRAVE_API_KEY[-8:]})")
    else:
        print("❌ Brave API key missing")
    
    if not OPENAI_API_KEY or not BRAVE_API_KEY:
        print("\n❌ Missing API keys. Please check your .env file.")
        return
    
    print(f"🧠 o4-mini reasoning effort: {O3_REASONING_EFFORT}")
    print()
    
    # Test query
    test_query = "How do I build a visual recipe in Dataiku?"
    print(f"📋 Test query: '{test_query}'\n")
    
    # Test Brave Search
    search_results = test_brave_search(test_query)
    
    if not search_results:
        print("\n❌ Cannot proceed without search results")
        return
    
    # Test OpenAI synthesis
    answer = test_openai_synthesis(test_query, search_results)
    
    if not answer:
        print("\n❌ Cannot proceed without AI synthesis")
        return
    
    # Show final result
    print("\n" + "="*80)
    print("📋 FINAL RESULT")
    print("="*80)
    
    final_response = format_response_with_sources(answer, search_results)
    print(final_response)
    
    print("\n" + "="*80)
    print("✅ All tests passed! Your Dataiku Agent should work in Slack.")
    print("="*80)

if __name__ == "__main__":
    main() 