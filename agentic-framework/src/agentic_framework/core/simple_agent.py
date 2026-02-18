from typing import Any, Dict, List, Union

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agentic_framework.constants import DEFAULT_MODEL
from agentic_framework.interfaces.base import Agent
from agentic_framework.registry import AgentRegistry


@AgentRegistry.register("simple", mcp_servers=None)
class SimpleAgent(Agent):
    """
    A simple agent implementation using LangChain.
    No MCP access (mcp_servers=None in registry).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, temperature: float = 0.0, **kwargs: Any) -> None:
        self.model = ChatOpenAI(model=model_name, temperature=temperature)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", "You are a helpful assistant."), ("user", "{input}")]
        )
        self.chain = self.prompt | self.model

    async def run(
        self,
        input_data: Union[str, List[BaseMessage]],
        config: Dict[str, Any] | None = None,
    ) -> Union[str, BaseMessage]:
        """
        Run the agent with the given input string.
        """
        if isinstance(input_data, str):
            response = await self.chain.ainvoke({"input": input_data})
            return str(response.content)

        raise NotImplementedError("SimpleAgent currently only supports string input.")

    def get_tools(self) -> List[Any]:
        return []
