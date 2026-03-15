import os
import pytest
import shutil
from unittest.mock import AsyncMock, patch
from pathlib import Path
from agntrick.agent import AgentBase
from agntrick.storage.database import Database
from langchain_core.messages import AIMessage

@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_persistence.db"

@pytest.fixture
def db(db_path):
    return Database(db_path)

class SimpleAgent(AgentBase):
    @property
    def system_prompt(self) -> str:
        return "You are a helpful assistant. Keep your answers very short."

async def mock_ainvoke(*args, **kwargs):
    # args[0] is self when patched on a class? No, side_effect on instance method patch...
    # Let's look at the traceback: args = ([SystemMessage(...), ...], {config})
    # So args[0] is the messages list.
    messages = args[0]
    content = messages[-1].content
    if "name is" in content:
        name = content.split("name is")[-1].strip(".")
        return AIMessage(content=f"Hello {name}!")
    elif "What is my name" in content:
        # In a real scenario, the LLM would see previous messages in the history.
        # LangGraph passes the full history to the model.
        # We can check if the history contains the name.
        names = [m.content.split("name is")[-1].strip(".") for m in messages if "name is" in m.content]
        if names:
            return AIMessage(content=f"Your name is {names[0]}.")
        return AIMessage(content="I don't know your name.")
    elif "favorite color is" in content:
        color = content.split("favorite color is")[-1].strip(".")
        return AIMessage(content=f"I remembered your favorite color is {color}.")
    elif "What is my favorite color" in content:
        colors = [m.content.split("favorite color is")[-1].strip(".") for m in messages if "favorite color is" in m.content]
        if colors:
            return AIMessage(content=f"Your favorite color is {colors[0]}.")
        return AIMessage(content="I don't know your favorite color.")
    return AIMessage(content="I am a mock response.")

@pytest.mark.asyncio
async def test_agent_persistence(db, db_path):
    """Test that an agent can remember context across different instances using the same DB."""
    thread_id = "test-session-123"
    
    with patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock_ainvoke):
        # 1. First session: Introduce ourselves
        async with db.get_checkpointer(is_async=True) as checkpointer1:
            agent1 = SimpleAgent(thread_id=thread_id, checkpointer=checkpointer1)
            response1 = await agent1.run("My name is Agntrick Test.")
            assert "Agntrick Test" in str(response1)
        
        # 2. Simulate "process restart"
        db2 = Database(db_path)
        async with db2.get_checkpointer(is_async=True) as checkpointer2:
            agent2 = SimpleAgent(thread_id=thread_id, checkpointer=checkpointer2)
            
            # 3. Second session: Ask who we are
            response2 = await agent2.run("What is my name?")
            
            # The agent should remember the name from the first session
            assert "Agntrick Test" in str(response2)
    
@pytest.mark.asyncio
async def test_different_threads_isolation(db):
    """Test that different thread IDs have isolated memories."""
    with patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock_ainvoke):
        async with db.get_checkpointer(is_async=True) as checkpointer:
            agent_a = SimpleAgent(thread_id="thread-a", checkpointer=checkpointer)
            await agent_a.run("My favorite color is Blue.")
            
            agent_b = SimpleAgent(thread_id="thread-b", checkpointer=checkpointer)
            await agent_b.run("My favorite color is Red.")
            
            resp_a = await agent_a.run("What is my favorite color?")
            resp_b = await agent_b.run("What is my favorite color?")
            
            assert "Blue" in str(resp_a)
            assert "Red" in str(resp_b)
            assert "Red" not in str(resp_a)
            assert "Blue" not in str(resp_b)
