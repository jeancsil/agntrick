from agentic_framework.interfaces.base import Tool


class CalculatorTool(Tool):
    """A simple calculator tool."""

    def invoke(self, input_str: str) -> str:
        """Evaluate a mathematical expression."""
        try:
            # WARNING: eval is dangerous, this is just for demo purposes
            return str(eval(input_str))
        except Exception as e:
            return f"Error: {e}"


class WeatherTool(Tool):
    """A mock weather tool."""

    def invoke(self, input_str: str) -> str:
        return f"The weather in {input_str} is currently sunny."
