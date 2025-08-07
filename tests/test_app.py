#!/usr/bin/env python3
"""
Test script for the LangGraph Dataiku Agent.

This script allows you to test the agent locally without needing Slack integration.
"""

import os
import sys
import time
from dotenv import load_dotenv

# Add src directory to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment variables
load_dotenv()

def test_environment():
    """Test that required environment variables are set."""
    print("🔍 Testing environment variables...")
    
    required_vars = ["OPENAI_API_KEY", "BRAVE_API_KEY"]
    missing_vars = []
    
    for var in required_vars:
        value = os.environ.get(var, "").strip()
        if not value:
            missing_vars.append(var)
        else:
            print(f"✅ {var}: {'*' * min(10, len(value))}...")
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file")
        return False
    
    print("✅ All environment variables are set")
    return True


def test_agent_import():
    """Test that we can import the agent."""
    print("\n🔍 Testing agent import...")
    
    try:
        from langgraph_agent import DataikuAgent, get_agent
        print("✅ Successfully imported LangGraph agent")
        return True
    except ImportError as e:
        print(f"❌ Failed to import agent: {e}")
        return False


def test_agent_initialization():
    """Test that we can initialize the agent."""
    print("\n🔍 Testing agent initialization...")
    
    try:
        from langgraph_agent import get_agent
        agent = get_agent()
        print("✅ Successfully initialized agent")
        print(f"   Agent type: {type(agent).__name__}")
        print(f"   Graph compiled: {agent.graph is not None}")
        return agent
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        return None


def test_search_tool():
    """Test the Brave Search tool directly."""
    print("\n🔍 Testing Brave Search tool...")
    
    try:
        from langgraph_agent import search_dataiku_brave
        
        print("   Searching for 'Dataiku machine learning'...")
        result = search_dataiku_brave.invoke({"query": "Dataiku machine learning"})
        
        if result["success"]:
            print(f"✅ Search successful! Found {len(result['results'])} results")
            if result["results"]:
                first_result = result["results"][0]
                print(f"   First result: {first_result['title'][:60]}...")
                print(f"   URL: {first_result['url']}")
                print(f"   Relevance: {first_result.get('relevance_score', 'N/A')}")
            return True
        else:
            print(f"❌ Search failed: {result['error']}")
            return False
    except Exception as e:
        print(f"❌ Search tool error: {e}")
        return False


def test_agent_query_processing():
    """Test the full agent query processing."""
    print("\n🔍 Testing agent query processing...")
    
    try:
        from langgraph_agent import get_agent
        agent = get_agent()
        
        test_queries = [
            "How do I create a visual recipe in Dataiku?",
            "What are the different user profiles in Dataiku?",
            "Error with machine learning model"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n   Test {i}: '{query}'")
            start_time = time.time()
            
            response = agent.process_query(
                query=query,
                thread_id=f"test_thread_{i}"
            )
            
            duration = time.time() - start_time
            print(f"   ⏱️  Processing time: {duration:.2f}s")
            print(f"   📝 Response length: {len(response)} characters")
            print(f"   🔤 Response preview: {response[:100]}...")
            
            if len(response) > 50:  # Reasonable response length
                print(f"   ✅ Query {i} processed successfully")
            else:
                print(f"   ⚠️  Query {i} response seems short")
        
        return True
        
    except Exception as e:
        print(f"❌ Agent query processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_memory():
    """Test that agent memory works across queries."""
    print("\n🔍 Testing agent memory...")
    
    try:
        from langgraph_agent import get_agent
        agent = get_agent()
        
        thread_id = "memory_test_thread"
        
        # First query
        print("   First query: 'What is Dataiku?'")
        response1 = agent.process_query("What is Dataiku?", thread_id=thread_id)
        print(f"   Response 1 length: {len(response1)} chars")
        
        # Follow-up query (should maintain context)
        print("   Follow-up query: 'How do I get started?'")
        response2 = agent.process_query("How do I get started?", thread_id=thread_id)
        print(f"   Response 2 length: {len(response2)} chars")
        
        if len(response1) > 50 and len(response2) > 50:
            print("✅ Memory test completed - responses generated")
            return True
        else:
            print("⚠️  Memory test completed but responses seem short")
            return False
            
    except Exception as e:
        print(f"❌ Memory test failed: {e}")
        return False


def interactive_mode():
    """Run interactive mode for manual testing."""
    print("\n🤖 Interactive Mode - Type 'quit' to exit")
    print("=" * 50)
    
    try:
        from langgraph_agent import get_agent
        agent = get_agent()
        thread_id = "interactive_session"
        
        while True:
            query = input("\n💬 Your question: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
                
            if not query:
                continue
                
            print("🤔 Agent is thinking...")
            start_time = time.time()
            
            try:
                response = agent.process_query(query, thread_id=thread_id)
                duration = time.time() - start_time
                
                print(f"\n🤖 Agent Response ({duration:.2f}s):")
                print("-" * 40)
                print(response)
                print("-" * 40)
                
            except Exception as e:
                print(f"❌ Error processing query: {e}")
    
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Interactive mode failed: {e}")


def main():
    """Run all tests."""
    print("🚀 LangGraph Dataiku Agent Test Suite")
    print("=" * 50)
    
    # Run tests in sequence
    tests = [
        ("Environment", test_environment),
        ("Import", test_agent_import),
        ("Initialization", test_agent_initialization),
        ("Search Tool", test_search_tool),
        ("Query Processing", test_agent_query_processing),
        ("Memory", test_agent_memory),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        result = test_func()
        if result:
            passed += 1
        
        # Small delay between tests
        time.sleep(0.5)
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Agent is working correctly.")
        
        # Ask if user wants interactive mode
        response = input("\n🤖 Would you like to try interactive mode? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            interactive_mode()
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        
        # Still offer interactive mode for debugging
        response = input("\n🤖 Would you like to try interactive mode anyway? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            interactive_mode()


if __name__ == "__main__":
    main()