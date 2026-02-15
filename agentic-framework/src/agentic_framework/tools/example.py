from agentic_framework.interfaces.base import Tool


class CalculatorTool(Tool):
    """A simple calculator tool."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Evaluate a mathematical expression. Input should be a valid Python expression string."

    def invoke(self, input_str: str) -> str:
        """Evaluate a mathematical expression."""
        try:
            # WARNING: eval is dangerous, this is just for demo purposes
            return str(eval(input_str))
        except Exception as e:
            return f"Error: {e}"


class WeatherTool(Tool):
    """A mock weather tool."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Get the current weather for a location."

    def invoke(self, input_str: str) -> str:
        return f"The weather in {input_str} is currently sunny."
