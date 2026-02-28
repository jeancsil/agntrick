from agentic_framework.tools.example import CalculatorTool, WeatherTool


def test_calculator_tool_success():
    tool = CalculatorTool()
    assert tool.invoke("2 + 2") == "4"


def test_calculator_tool_error():
    tool = CalculatorTool()
    result = tool.invoke("1 / 0")
    assert result.startswith("Error:")


def test_weather_tool():
    tool = WeatherTool()
    assert "Lisbon" in tool.invoke("Lisbon")


def test_calculator_blocks_dangerous_operations():
    tool = CalculatorTool()
    # Test that function calls are blocked
    assert "not allowed" in tool.invoke("__import__('os')")
    assert "not allowed" in tool.invoke("print('hello')")
    # Test that attribute access is blocked (returns error message)
    result = tool.invoke("open('/etc/passwd').read()")
    assert "Error" in result
    # Test that empty expressions are blocked
    result2 = tool.invoke("")
    assert "Error" in result2


def test_calculator_safe_operations():
    tool = CalculatorTool()
    # Test all supported operations
    assert tool.invoke("2 + 2") == "4"
    assert tool.invoke("10 - 3") == "7"
    assert tool.invoke("3 * 4") == "12"
    assert tool.invoke("15 / 3") == "5.0"
    assert tool.invoke("15 // 4") == "3"
    assert tool.invoke("15 % 4") == "3"
    assert tool.invoke("2 ** 3") == "8"
    assert tool.invoke("-5") == "-5"
    assert tool.invoke("+5") == "5"
    assert tool.invoke("abs(-5)") == "5"
    assert tool.invoke("round(3.7)") == "4"
    assert tool.invoke("min(1, 5, 3)") == "1"
    assert tool.invoke("max(1, 5, 3)") == "5"
    assert tool.invoke("sum([1, 2, 3])") == "6"
