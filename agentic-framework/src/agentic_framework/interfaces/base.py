from abc import ABC, abstractmethod
from typing import Any, List, Union

from langchain_core.messages import BaseMessage


class Agent(ABC):
    """Abstract Base Class for an Agent."""

    @abstractmethod
    def run(self, input_data: Union[str, List[BaseMessage]]) -> Union[str, BaseMessage]:
        """Run the agent with the given input."""
        pass

    @abstractmethod
    def get_tools(self) -> List[Any]:
        """Return available tools for this agent."""
        pass


class Tool(ABC):
    """Abstract Base Class for a Tool."""

    @abstractmethod
    def invoke(self, input_str: str) -> str:
        """Execute the tool logic."""
        pass
