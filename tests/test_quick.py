#!/usr/bin/env python3
"""
Quick test script for the LangGraph Dataiku Agent.
Simply run: python quick_test.py
"""

import os
import sys
import time
from dotenv import load_dotenv

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment variables
load_dotenv()

def test_single_query():
    """Test a single query with the agent."""
    print("🚀 Testing LangGraph Dataiku Agent")
    print("=" * 50)
    
    try:
        from langgraph_agent import get_agent
        
        # Initialize agent
        print("🔧 Initializing agent...")
        agent = get_agent()
        print("✅ Agent initialized successfully!")
        
        # Test query
        query = "How do I create a machine learning model in Dataiku?"
        print(f"\n💬 Query: {query}")
        print("🤔 Agent is processing...")
        
        start_time = time.time()
        response = agent.process_query(query, thread_id="test_session")
        duration = time.time() - start_time
        
        print(f"\n🤖 Agent Response ({duration:.2f}s):")
        print("=" * 50)
        print(response)
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def interactive_test():
    """Run interactive test session."""
    print("\n🔄 Interactive Mode - Type 'quit' to exit")
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

if __name__ == "__main__":
    # Quick test first
    success = test_single_query()
    
    if success:
        print("\n🎉 Agent is working correctly!")
        
        # Ask for interactive mode
        try:
            response = input("\nWould you like to try interactive mode? (y/n): ").strip().lower()
            if response in ['y', 'yes']:
                interactive_test()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
    else:
        print("\n❌ Agent test failed. Check the error above.")