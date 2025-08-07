"""
LangGraph-based AI Agent for Dataiku Slack Assistant.

Implements a sophisticated AI agent using LangGraph with unified services
for search, synthesis, and response formatting.
"""

import time
from typing import List, Dict, Any, Optional, TypedDict

from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver

from ..core.clients import get_logger
from ..services.search_service import search_brave_with_metadata
from ..services.ai_service import synthesize_answer
from ..utils.text_processing import format_response_with_sources
from ..utils.fallback_responses import generate_fallback_response

logger = get_logger()

class AgentState(TypedDict):
    """State definition for the LangGraph agent."""
    query: str
    original_query: str
    search_results: List[Dict[str, Any]]
    processed_results: List[Dict[str, Any]]
    answer: str
    confidence_score: float
    needs_clarification: bool
    conversation_history: List[Dict[str, Any]]
    search_attempts: int
    error_context: Optional[str]
    final_response: str

@tool
def search_dataiku_brave(query: str) -> Dict[str, Any]:
    """
    Search for Dataiku-related information using Brave Search API.
    
    Args:
        query: The search query to execute
        
    Returns:
        Dictionary containing search results and metadata
    """
    logger.info("brave_search_tool_called", query=query[:100])
    
    # Use the unified search service
    return search_brave_with_metadata(query)

# Agent Node Functions
def analyze_query_node(state: AgentState) -> AgentState:
    """Analyze the incoming query and determine the best approach."""
    query = state["query"]
    
    logger.info("analyzing_query", query=query[:100])
    
    # Simple query classification
    query_lower = query.lower()
    
    # Determine if this needs clarification
    needs_clarification = False
    confidence_score = 1.0
    
    if len(query.strip()) < 10:
        needs_clarification = True
        confidence_score = 0.3
    elif any(word in query_lower for word in ["help", "what", "how", "why", "explain"]):
        confidence_score = 0.8
    elif any(word in query_lower for word in ["error", "problem", "issue", "not working"]):
        confidence_score = 0.9
    
    state["needs_clarification"] = needs_clarification
    state["confidence_score"] = confidence_score
    state["search_attempts"] = 0
    
    logger.info("query_analysis_completed", 
               needs_clarification=needs_clarification,
               confidence_score=confidence_score)
    
    return state

def search_node(state: AgentState) -> AgentState:
    """Execute search using the Brave Search tool."""
    query = state["query"]
    search_attempts = state.get("search_attempts", 0)
    
    logger.info("executing_search", query=query[:100], attempt=search_attempts + 1)
    
    # Use the search tool
    search_result = search_dataiku_brave.invoke({"query": query})
    
    state["search_attempts"] = search_attempts + 1
    
    if search_result["success"]:
        state["search_results"] = search_result["results"]
        state["processed_results"] = search_result["results"]  # For now, same as raw results
        logger.info("search_completed_successfully", 
                   result_count=len(search_result["results"]))
    else:
        state["search_results"] = []
        state["processed_results"] = []
        state["error_context"] = search_result.get("error", "Unknown search error")
        logger.error("search_failed", error=search_result.get("error"))
    
    return state

def synthesize_answer_node(state: AgentState) -> AgentState:
    """Synthesize an answer using the unified AI service."""
    query = state["query"]
    search_results = state.get("search_results", [])
    
    logger.info("synthesizing_answer", 
               query=query[:100],
               result_count=len(search_results))
    
    try:
        # Use the unified AI service
        answer = synthesize_answer(query, search_results)
        state["answer"] = answer or ""
        
        logger.info("answer_synthesis_completed", 
                   answer_length=len(answer) if answer else 0)
        
    except Exception as e:
        logger.error("synthesis_failed", error=str(e), error_type=type(e).__name__)
        state["answer"] = ""
        state["error_context"] = f"Synthesis error: {str(e)}"
    
    return state

def format_response_node(state: AgentState) -> AgentState:
    """Format the final response with proper Slack formatting and URL handling."""
    answer = state.get("answer", "")
    search_results = state.get("search_results", [])
    error_context = state.get("error_context")
    
    logger.info("formatting_response", 
               has_answer=bool(answer),
               has_search_results=bool(search_results),
               has_error=bool(error_context))
    
    if error_context and not answer:
        # Generate fallback response
        final_response = generate_fallback_response(state["original_query"])
    elif answer:
        # Format the answer with proper URL handling using unified utilities
        final_response = format_response_with_sources(answer, search_results)
    else:
        final_response = "I couldn't find any relevant information about your query. Please try rephrasing your question or asking about a different aspect of Dataiku."
    
    state["final_response"] = final_response
    
    logger.info("response_formatting_completed", 
               response_length=len(final_response))
    
    return state

# Conditional edge functions
def should_search(state: AgentState) -> str:
    """Decide whether to search or ask for clarification."""
    if state.get("needs_clarification", False):
        return "clarify"
    return "search"

def should_retry_search(state: AgentState) -> str:
    """Decide whether to retry search or proceed to synthesis."""
    search_results = state.get("search_results", [])
    search_attempts = state.get("search_attempts", 0)
    
    if len(search_results) == 0 and search_attempts < 2:
        return "retry_search"
    return "synthesize"

def should_format_response(state: AgentState) -> str:
    """Always proceed to format response."""
    return "format"

class DataikuAgent:
    """LangGraph-based Dataiku AI Agent."""
    
    def __init__(self):
        self.memory = MemorySaver()
        self.graph = self._build_graph()
        
    def _build_graph(self) -> CompiledStateGraph:
        """Build the LangGraph state graph."""
        # Create the state graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("analyze", analyze_query_node)
        workflow.add_node("search", search_node)
        workflow.add_node("synthesize", synthesize_answer_node)
        workflow.add_node("format", format_response_node)
        
        # Add edges
        workflow.add_edge(START, "analyze")
        
        # Conditional edges
        workflow.add_conditional_edges(
            "analyze",
            should_search,
            {
                "search": "search",
                "clarify": "format"  # Skip to format for clarification
            }
        )
        
        workflow.add_conditional_edges(
            "search",
            should_retry_search,
            {
                "retry_search": "search",
                "synthesize": "synthesize"
            }
        )
        
        workflow.add_conditional_edges(
            "synthesize",
            should_format_response,
            {
                "format": "format"
            }
        )
        
        workflow.add_edge("format", END)
        
        # Compile the graph
        return workflow.compile(checkpointer=self.memory)
    
    def process_query(self, query: str, thread_id: str = None) -> str:
        """
        Process a user query through the agent workflow.
        
        Args:
            query: The user's question
            thread_id: Optional thread ID for conversation memory
            
        Returns:
            The formatted response
        """
        start_time = time.time()
        
        # Prepare initial state
        initial_state = {
            "query": query,
            "original_query": query,
            "search_results": [],
            "processed_results": [],
            "answer": "",
            "confidence_score": 0.0,
            "needs_clarification": False,
            "conversation_history": [],
            "search_attempts": 0,
            "error_context": None,
            "final_response": ""
        }
        
        # Configure run parameters
        config = {"configurable": {"thread_id": thread_id or "default"}}
        
        logger.info("agent_processing_started", 
                   query=query[:100],
                   thread_id=thread_id)
        
        try:
            # Run the agent workflow
            result = self.graph.invoke(initial_state, config=config)
            
            final_response = result.get("final_response", "I couldn't process your query.")
            
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info("agent_processing_completed", 
                       query=query[:100],
                       duration_ms=duration_ms,
                       response_length=len(final_response))
            
            return final_response
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error("agent_processing_failed", 
                        error=str(e),
                        error_type=type(e).__name__,
                        query=query[:100],
                        duration_ms=duration_ms)
            
            # Return fallback response
            return generate_fallback_response(query)
    
    def stream_query(self, query: str, thread_id: str = None):
        """
        Stream the agent processing with intermediate updates.
        
        Args:
            query: The user's question
            thread_id: Optional thread ID for conversation memory
            
        Yields:
            State updates during processing
        """
        initial_state = {
            "query": query,
            "original_query": query,
            "search_results": [],
            "processed_results": [],
            "answer": "",
            "confidence_score": 0.0,
            "needs_clarification": False,
            "conversation_history": [],
            "search_attempts": 0,
            "error_context": None,
            "final_response": ""
        }
        
        config = {"configurable": {"thread_id": thread_id or "default"}}
        
        try:
            for chunk in self.graph.stream(initial_state, config=config):
                yield chunk
        except Exception as e:
            logger.error("agent_streaming_failed", error=str(e))
            yield {"error": str(e)}

# Global agent instance
_agent_instance = None

def get_agent() -> DataikuAgent:
    """Get or create the global agent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = DataikuAgent()
    return _agent_instance