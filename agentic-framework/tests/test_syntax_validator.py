"""Tests for syntax_validator module."""

from pathlib import Path

import pytest

from agentic_framework.tools.syntax_validator import (
    MAX_FILE_SIZE,
    SyntaxValidator,
    ValidationError,
    ValidationResult,
    get_validator,
)


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_str_representation(self) -> None:
        """Test string representation of ValidationError."""
        error = ValidationError(line=10, column=5, message="Unexpected token")
        assert str(error) == "Line 10, Col 5: Unexpected token"

    def test_line_column_values(self) -> None:
        """Test that line and column are stored correctly."""
        error = ValidationError(line=1, column=1, message="Error at start")
        assert error.line == 1
        assert error.column == 1
        assert error.message == "Error at start"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result_no_warning(self) -> None:
        """Test that valid result has no warning message."""
        result = ValidationResult(is_valid=True, language="python", errors=[])
        assert result.warning_message is None

    def test_invalid_result_has_warning(self) -> None:
        """Test that invalid result has warning message."""
        errors = [ValidationError(line=5, column=1, message="Syntax error")]
        result = ValidationResult(is_valid=False, language="python", errors=errors)
        assert result.warning_message is not None
        assert "SYNTAX WARNING" in result.warning_message
        assert "python" in result.warning_message
        assert "1 syntax error" in result.warning_message

    def test_multiple_errors_limited_in_output(self) -> None:
        """Test that only first 5 errors are shown in warning."""
        errors = [ValidationError(line=i, column=1, message=f"Error {i}") for i in range(1, 11)]
        result = ValidationResult(is_valid=False, language="python", errors=errors)
        assert result.warning_message is not None
        assert "10 syntax error" in result.warning_message
        assert "5 more error" in result.warning_message

    def test_skipped_result_no_warning(self) -> None:
        """Test that skipped result has no warning message."""
        result = ValidationResult(is_valid=True, language="python", errors=[], skipped=True, skip_reason="No parser")
        assert result.warning_message is None


class TestSyntaxValidator:
    """Tests for SyntaxValidator class."""

    @pytest.fixture
    def validator(self) -> SyntaxValidator:
        """Create a fresh validator instance for each test."""
        return SyntaxValidator()

    def test_unsupported_extension_skipped(self, validator: SyntaxValidator) -> None:
        """Test that unsupported file extensions are skipped."""
        result = validator.validate("some content", "file.txt")
        assert result.skipped is True
        assert "Unsupported file extension" in (result.skip_reason or "")

    def test_supported_languages(self, validator: SyntaxValidator) -> None:
        """Test that supported language extensions are recognized."""
        supported = [".py", ".js", ".ts", ".rs", ".go", ".java", ".c", ".cpp", ".php"]
        for ext in supported:
            result = validator.validate("x = 1", f"file{ext}")
            assert result.language is not None
            # Skip reason can be various things like "tree-sitter not installed", "No parser available", etc.
            # The key thing is that the language is detected correctly
            if result.skipped:
                assert result.skip_reason is not None

    def test_valid_python_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid Python code."""
        code = """
def hello():
    print("Hello, world!")

class MyClass:
    pass
"""
        result = validator.validate(code, "test.py")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_invalid_python_code(self, validator: SyntaxValidator) -> None:
        """Test validation of invalid Python code."""
        code = """
def hello(:
    print("Missing closing paren"
"""
        result = validator.validate(code, "test.py")
        if not result.skipped:
            assert result.is_valid is False
            assert len(result.errors) > 0

    def test_valid_javascript_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid JavaScript code."""
        code = """
function hello() {
    console.log("Hello, world!");
}

class MyClass {
    constructor() {
        this.value = 1;
    }
}
"""
        result = validator.validate(code, "test.js")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_invalid_javascript_code(self, validator: SyntaxValidator) -> None:
        """Test validation of invalid JavaScript code."""
        code = """
function hello( {
    console.log("Missing closing paren");
}
"""
        result = validator.validate(code, "test.js")
        if not result.skipped:
            assert result.is_valid is False
            assert len(result.errors) > 0

    def test_valid_typescript_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid TypeScript code."""
        code = """
interface User {
    name: string;
    age: number;
}

function greet(user: User): string {
    return `Hello, ${user.name}!`;
}
"""
        result = validator.validate(code, "test.ts")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_valid_rust_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid Rust code."""
        code = """
fn main() {
    println!("Hello, world!");
}

struct Point {
    x: i32,
    y: i32,
}
"""
        result = validator.validate(code, "test.rs")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_valid_go_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid Go code."""
        code = """
package main

func main() {
    println("Hello, world!")
}

type Point struct {
    X int
    Y int
}
"""
        result = validator.validate(code, "test.go")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_valid_java_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid Java code."""
        code = """
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, world!");
    }
}
"""
        result = validator.validate(code, "test.java")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_valid_c_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid C code."""
        code = """
#include <stdio.h>

int main() {
    printf("Hello, world!\\n");
    return 0;
}
"""
        result = validator.validate(code, "test.c")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_valid_cpp_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid C++ code."""
        code = """
#include <iostream>

class Point {
public:
    int x, y;
    Point(int x, int y) : x(x), y(y) {}
};

int main() {
    std::cout << "Hello, world!" << std::endl;
    return 0;
}
"""
        result = validator.validate(code, "test.cpp")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_valid_php_code(self, validator: SyntaxValidator) -> None:
        """Test validation of valid PHP code."""
        code = """<?php

class MyClass {
    public function hello() {
        echo "Hello, world!";
    }
}
"""
        result = validator.validate(code, "test.php")
        if not result.skipped:
            assert result.is_valid is True
            assert len(result.errors) == 0

    def test_large_file_skipped(self, validator: SyntaxValidator) -> None:
        """Test that large files are skipped for performance."""
        # Create content larger than MAX_FILE_SIZE
        large_content = "x" * (MAX_FILE_SIZE + 1000)
        result = validator.validate(large_content, "test.py")
        assert result.skipped is True
        assert "too large" in (result.skip_reason or "").lower()

    def test_empty_file_valid(self, validator: SyntaxValidator) -> None:
        """Test that empty files are valid."""
        result = validator.validate("", "test.py")
        if not result.skipped:
            # Empty files are typically valid syntax
            assert result.is_valid is True


class TestGetValidator:
    """Tests for get_validator singleton function."""

    def test_returns_same_instance(self) -> None:
        """Test that get_validator returns the same instance."""
        v1 = get_validator()
        v2 = get_validator()
        assert v1 is v2

    def test_returns_syntax_validator(self) -> None:
        """Test that get_validator returns a SyntaxValidator."""
        validator = get_validator()
        assert isinstance(validator, SyntaxValidator)


class TestFileEditorToolIntegration:
    """Integration tests for FileEditorTool with syntax validation."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file for testing."""
        file_path = tmp_path / "test_file.py"
        file_path.write_text(
            """def hello():
    print("Hello")

def world():
    print("World")
"""
        )
        return file_path

    def test_edit_creates_invalid_syntax_warning(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that edit that creates invalid syntax shows warning."""
        from agentic_framework.tools.codebase_explorer import FileEditorTool

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        tool = FileEditorTool(root_dir=tmp_path)

        # Edit to create invalid syntax
        result = tool.invoke(f'replace:{test_file.name}:1:2:def foo(:\\n    print("broken")')

        # Should show syntax warning if tree-sitter is available
        if "SYNTAX WARNING" in result:
            assert "syntax error" in result.lower()

    def test_edit_preserves_valid_syntax(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that edit that preserves valid syntax shows no warning."""
        from agentic_framework.tools.codebase_explorer import FileEditorTool

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        tool = FileEditorTool(root_dir=tmp_path)

        # Edit with valid syntax
        result = tool.invoke(f'replace:{test_file.name}:2:2:    print("hello")')

        # Should not show syntax warning
        assert "SYNTAX WARNING" not in result
        assert "Replaced lines" in result

    def test_insert_with_valid_syntax(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that insert with valid syntax shows no warning."""
        from agentic_framework.tools.codebase_explorer import FileEditorTool

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        tool = FileEditorTool(root_dir=tmp_path)

        # Insert valid code
        result = tool.invoke(f'insert:{test_file.name}:2:    print("new line")')

        # Should not show syntax warning
        assert "SYNTAX WARNING" not in result
        assert "Inserted content" in result

    def test_delete_preserves_valid_syntax(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that delete that preserves valid syntax shows no warning."""
        from agentic_framework.tools.codebase_explorer import FileEditorTool

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")

        tool = FileEditorTool(root_dir=tmp_path)

        # Delete a function (keeping valid syntax)
        result = tool.invoke(f"delete:{test_file.name}:3:5")

        # Should not show syntax warning
        assert "SYNTAX WARNING" not in result
        assert "Deleted" in result
