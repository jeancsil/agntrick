"""Tests for codebase explorer tools."""

import tempfile
from pathlib import Path

import pytest

from agentic_framework.tools.codebase_explorer import (
    LANGUAGE_EXTENSIONS,
    LANGUAGE_PATTERNS,
    FileEditorTool,
    FileFragmentReaderTool,
    FileOutlinerTool,
    StructureExplorerTool,
)


class TestLanguageDetection:
    """Tests for language detection by file extension."""

    def test_python_extensions(self):
        assert LANGUAGE_EXTENSIONS[".py"] == "python"
        assert LANGUAGE_EXTENSIONS[".pyi"] == "python"

    def test_javascript_extensions(self):
        assert LANGUAGE_EXTENSIONS[".js"] == "javascript"
        assert LANGUAGE_EXTENSIONS[".mjs"] == "javascript"
        assert LANGUAGE_EXTENSIONS[".cjs"] == "javascript"

    def test_typescript_extensions(self):
        assert LANGUAGE_EXTENSIONS[".ts"] == "typescript"
        assert LANGUAGE_EXTENSIONS[".tsx"] == "typescript"

    def test_rust_extension(self):
        assert LANGUAGE_EXTENSIONS[".rs"] == "rust"

    def test_go_extension(self):
        assert LANGUAGE_EXTENSIONS[".go"] == "go"

    def test_java_extension(self):
        assert LANGUAGE_EXTENSIONS[".java"] == "java"

    def test_c_cpp_extensions(self):
        assert LANGUAGE_EXTENSIONS[".c"] == "c"
        assert LANGUAGE_EXTENSIONS[".h"] == "c"
        assert LANGUAGE_EXTENSIONS[".cpp"] == "cpp"
        assert LANGUAGE_EXTENSIONS[".hpp"] == "cpp"

    def test_php_extension(self):
        assert LANGUAGE_EXTENSIONS[".php"] == "php"


class TestFileOutlinerTool:
    """Tests for FileOutlinerTool with multi-language support."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def outliner(self, temp_dir):
        return FileOutlinerTool(str(temp_dir))

    def test_python_outline(self, outliner, temp_dir):
        """Test Python file outline extraction."""
        code = '''
import os

class MyAgent:
    """A simple agent."""

    def __init__(self):
        pass

    async def run(self, input_data):
        return "done"

def helper_function():
    pass
'''
        (temp_dir / "test.py").write_text(code)
        result = outliner.invoke("test.py")

        assert isinstance(result, list)
        assert len(result) == 4

        signatures = [item["signature"] for item in result]
        lines = [item["line"] for item in result]

        assert any("class MyAgent" in s for s in signatures)
        assert any("def __init__" in s for s in signatures)
        assert any("async def run" in s for s in signatures)
        assert any("def helper_function" in s for s in signatures)

        # Verify line numbers
        assert 4 in lines  # class
        assert 7 in lines  # def __init__
        assert 10 in lines  # async def run

    def test_javascript_outline(self, outliner, temp_dir):
        """Test JavaScript file outline extraction."""
        code = """
export class UserService {
    constructor() {}

    async fetchUser(id) {
        return fetch(`/users/${id}`);
    }
}

export function helper() {
    return "helper";
}

const processItem = (item) => {
    return item;
};

const asyncProcess = async (data) => {
    return data;
};
"""
        (temp_dir / "test.js").write_text(code)
        result = outliner.invoke("test.js")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        assert any("class UserService" in s for s in signatures)
        assert any("function helper" in s for s in signatures)
        assert any("processItem" in s for s in signatures)
        assert any("asyncProcess" in s for s in signatures)

    def test_typescript_outline(self, outliner, temp_dir):
        """Test TypeScript file outline extraction."""
        code = """
interface User {
    id: number;
    name: string;
}

type UserRole = "admin" | "user";

export class UserService {
    async getUser(id: number): Promise<User> {
        return {} as User;
    }
}

export enum Status {
    Active,
    Inactive
}

abstract class BaseService {
    abstract connect(): void;
}
"""
        (temp_dir / "test.ts").write_text(code)
        result = outliner.invoke("test.ts")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        assert any("interface User" in s for s in signatures)
        assert any("type UserRole" in s for s in signatures)
        assert any("class UserService" in s for s in signatures)
        assert any("enum Status" in s for s in signatures)
        assert any("abstract class BaseService" in s for s in signatures)

    def test_rust_outline(self, outliner, temp_dir):
        """Test Rust file outline extraction."""
        code = """
pub struct User {
    pub name: String,
}

struct PrivateData {
    id: u64,
}

pub enum Status {
    Active,
    Inactive,
}

pub trait Repository {
    fn find(&self, id: u64) -> Option<User>;
}

impl User {
    pub fn new(name: String) -> Self {
        Self { name }
    }
}

pub fn create_user(name: &str) -> User {
    User { name: name.to_string() }
}

pub async fn fetch_user(id: u64) -> Result<User, Error> {
    Ok(User { name: "test".into() })
}

pub mod models {
    pub struct Model {}
}
"""
        (temp_dir / "test.rs").write_text(code)
        result = outliner.invoke("test.rs")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        assert any("struct User" in s for s in signatures)
        assert any("struct PrivateData" in s for s in signatures)
        assert any("enum Status" in s for s in signatures)
        assert any("trait Repository" in s for s in signatures)
        assert any("impl User" in s for s in signatures)
        assert any("fn create_user" in s for s in signatures)
        assert any("fn fetch_user" in s for s in signatures)
        assert any("mod models" in s for s in signatures)

    def test_go_outline(self, outliner, temp_dir):
        """Test Go file outline extraction."""
        code = """
package main

type User struct {
    Name string
    Age  int
}

type UserRepository interface {
    FindByID(id int) (*User, error)
    Save(user *User) error
}

type Handler func(w http.ResponseWriter, r *http.Request)

func NewUser(name string, age int) *User {
    return &User{Name: name, Age: age}
}

func (u *User) Greet() string {
    return fmt.Sprintf("Hello, %s", u.Name)
}

func (u *User) SetAge(age int) {
    u.Age = age
}
"""
        (temp_dir / "test.go").write_text(code)
        result = outliner.invoke("test.go")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        assert any("type User struct" in s for s in signatures)
        assert any("type UserRepository interface" in s for s in signatures)
        assert any("type Handler func" in s for s in signatures)
        assert any("func NewUser" in s for s in signatures)
        assert any("(u *User) Greet" in s for s in signatures)
        assert any("(u *User) SetAge" in s for s in signatures)

    def test_java_outline(self, outliner, temp_dir):
        """Test Java file outline extraction."""
        code = """
package com.example;

import java.util.List;

public class UserService {
    private String name;

    public UserService(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    private void processInternal() {
        // internal logic
    }

    public static UserService createDefault() {
        return new UserService("default");
    }
}

interface Repository<T> {
    T findById(long id);
    void save(T entity);
}

enum Status {
    ACTIVE,
    INACTIVE
}

abstract class BaseService {
    public abstract void initialize();
}
"""
        (temp_dir / "Test.java").write_text(code)
        result = outliner.invoke("Test.java")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        assert any("class UserService" in s for s in signatures)
        assert any("interface Repository" in s for s in signatures)
        assert any("enum Status" in s for s in signatures)
        assert any("abstract class BaseService" in s for s in signatures)
        # Methods
        assert any("UserService(" in s for s in signatures)
        assert any("getName(" in s for s in signatures)
        assert any("processInternal(" in s for s in signatures)
        assert any("createDefault(" in s for s in signatures)

    def test_c_outline(self, outliner, temp_dir):
        """Test C file outline extraction."""
        code = """
#include <stdio.h>

typedef struct {
    int x;
    int y;
} Point;

struct User {
    char name[50];
    int age;
};

enum Status {
    STATUS_OK,
    STATUS_ERROR
};

int add(int a, int b) {
    return a + b;
}

void print_hello(void) {
    printf("Hello\\n");
}

double calculate(double x) {
    return x * 2.0;
}
"""
        (temp_dir / "test.c").write_text(code)
        result = outliner.invoke("test.c")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        # Note: typedef struct { ... } Point; matches "typedef struct" line, not "Point"
        assert any("typedef struct" in s for s in signatures)
        assert any("struct User" in s for s in signatures)
        assert any("enum Status" in s for s in signatures)
        assert any("int add" in s for s in signatures)
        assert any("void print_hello" in s for s in signatures)
        assert any("double calculate" in s for s in signatures)

    def test_cpp_outline(self, outliner, temp_dir):
        """Test C++ file outline extraction."""
        code = """
#include <string>
#include <vector>

namespace myapp {

class User {
private:
    std::string name;
public:
    User(const std::string& name);
    std::string getName() const;
};

struct Point {
    int x, y;
};

template<typename T> class Container {
public:
    void add(const T& item);
    T get(int index) const;
};

} // namespace myapp

void helper_function() {
    // helper
}
"""
        (temp_dir / "test.cpp").write_text(code)
        result = outliner.invoke("test.cpp")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        assert any("class User" in s for s in signatures)
        assert any("struct Point" in s for s in signatures)
        assert any("namespace myapp" in s for s in signatures)
        assert any("template" in s and "Container" in s for s in signatures)
        assert any("helper_function" in s for s in signatures)

    def test_php_outline(self, outliner, temp_dir):
        """Test PHP file outline extraction."""
        code = """<?php

namespace App\\Services;

abstract class AbstractService {
    abstract protected function initialize(): void;
}

final class UserService extends AbstractService {
    private $repository;

    public function __construct($repository) {
        $this->repository = $repository;
    }

    public function getUser(int $id): ?User {
        return $this->repository->find($id);
    }

    private function validateData(array $data): bool {
        return true;
    }

    public static function createDefault(): self {
        return new self(null);
    }
}

interface UserRepositoryInterface {
    public function find(int $id): ?User;
    public function save(User $user): bool;
}

trait LoggingTrait {
    protected function log(string $message): void {
        echo $message;
    }
}
"""
        (temp_dir / "test.php").write_text(code)
        result = outliner.invoke("test.php")

        assert isinstance(result, list)
        signatures = [item["signature"] for item in result]

        assert any("class AbstractService" in s for s in signatures)
        assert any("final class UserService" in s for s in signatures)
        assert any("interface UserRepositoryInterface" in s for s in signatures)
        assert any("trait LoggingTrait" in s for s in signatures)
        # Methods
        assert any("function __construct" in s for s in signatures)
        assert any("function getUser" in s for s in signatures)
        assert any("function validateData" in s for s in signatures)
        assert any("static function createDefault" in s for s in signatures)

    def test_unsupported_file_type(self, outliner, temp_dir):
        """Test that unsupported file types return an error."""
        (temp_dir / "test.xyz").write_text("some content")
        result = outliner.invoke("test.xyz")

        assert isinstance(result, str)
        assert "Error" in result
        assert "Unsupported file type" in result

    def test_file_not_found(self, outliner):
        """Test that non-existent files return an error."""
        result = outliner.invoke("nonexistent.py")

        assert isinstance(result, str)
        assert "Error" in result
        assert "not found" in result

    def test_empty_file(self, outliner, temp_dir):
        """Test that empty files return empty outline."""
        (temp_dir / "empty.py").write_text("")
        result = outliner.invoke("empty.py")

        assert isinstance(result, list)
        assert len(result) == 0

    def test_output_has_line_numbers(self, outliner, temp_dir):
        """Test that output includes line numbers."""
        code = """def foo():
    pass

class Bar:
    pass
"""
        (temp_dir / "test.py").write_text(code)
        result = outliner.invoke("test.py")

        assert isinstance(result, list)
        for item in result:
            assert "line" in item
            assert isinstance(item["line"], int)
            assert "signature" in item
            assert isinstance(item["signature"], str)


class TestFileFragmentReaderTool:
    """Tests for FileFragmentReaderTool."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def reader(self, temp_dir):
        return FileFragmentReaderTool(str(temp_dir))

    def test_read_fragment(self, reader, temp_dir):
        """Test reading a fragment of a file."""
        content = "line1\nline2\nline3\nline4\nline5"
        (temp_dir / "test.txt").write_text(content)

        result = reader.invoke("test.txt:2:4")
        assert result == "line2\nline3\nline4\n"

    def test_invalid_format(self, reader):
        """Test that invalid format returns error."""
        result = reader.invoke("invalid")
        assert "Error" in result
        assert "Invalid input format" in result


class TestStructureExplorerTool:
    """Tests for StructureExplorerTool."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def explorer(self, temp_dir):
        return StructureExplorerTool(str(temp_dir))

    def test_discover_structure(self, explorer, temp_dir):
        """Test directory structure discovery."""
        (temp_dir / "file1.py").write_text("# file1")
        (temp_dir / "file2.py").write_text("# file2")
        (temp_dir / "subdir").mkdir()
        (temp_dir / "subdir" / "file3.py").write_text("# file3")

        result = explorer.invoke("2")

        assert result["type"] == "directory"
        children_names = [c["name"] for c in result["children"]]
        assert "file1.py" in children_names
        assert "file2.py" in children_names
        assert "subdir" in children_names


class TestLanguagePatterns:
    """Tests to verify all language patterns are valid regex."""

    def test_all_patterns_compile(self):
        """Verify all patterns in LANGUAGE_PATTERNS compile successfully."""
        import re

        for language, patterns in LANGUAGE_PATTERNS.items():
            for pattern in patterns:
                # Should not raise exception
                compiled = re.compile(pattern)
                assert compiled is not None


class TestFileEditorTool:
    """Tests for FileEditorTool."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def editor(self, temp_dir):
        return FileEditorTool(str(temp_dir))

    # Replace tests
    def test_replace_lines(self, editor, temp_dir):
        """Test replacing a range of lines."""
        (temp_dir / "test.py").write_text("line1\nline2\nline3\nline4\n")
        result = editor.invoke("replace:test.py:2:3:new_line2\nnew_line3")
        assert "Replaced lines 2-3" in result
        content = (temp_dir / "test.py").read_text()
        assert "line1" in content
        assert "new_line2" in content
        assert "new_line3" in content
        assert "line4" in content

    def test_replace_single_line(self, editor, temp_dir):
        """Test replacing a single line."""
        (temp_dir / "test.py").write_text("line1\nline2\nline3\n")
        result = editor.invoke("replace:test.py:2:2:replaced")
        assert "Replaced lines 2-2" in result
        content = (temp_dir / "test.py").read_text()
        assert content == "line1\nreplaced\nline3\n"

    def test_replace_all_lines(self, editor, temp_dir):
        """Test replacing all lines in file."""
        (temp_dir / "test.py").write_text("old1\nold2\nold3\n")
        result = editor.invoke("replace:test.py:1:3:new_content")
        assert "Replaced lines 1-3" in result
        content = (temp_dir / "test.py").read_text()
        assert content == "new_content\n"

    # Insert tests
    def test_insert_after_line(self, editor, temp_dir):
        """Test inserting after a specific line."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        result = editor.invoke("insert:test.py:1:inserted")
        assert "Inserted content after line 1" in result
        content = (temp_dir / "test.py").read_text()
        lines = content.split("\n")
        assert lines[0] == "line1"
        assert lines[1] == "inserted"
        assert lines[2] == "line2"

    def test_insert_before_line(self, editor, temp_dir):
        """Test inserting before a specific line."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        result = editor.invoke("insert:test.py:before_1:inserted")
        assert "Inserted content before line 1" in result
        content = (temp_dir / "test.py").read_text()
        lines = content.split("\n")
        assert lines[0] == "inserted"
        assert lines[1] == "line1"

    def test_insert_at_beginning(self, editor, temp_dir):
        """Test inserting at the beginning of file."""
        (temp_dir / "test.py").write_text("line1\n")
        result = editor.invoke("insert:test.py:0:first_line")
        assert "at beginning" in result
        content = (temp_dir / "test.py").read_text()
        assert content.startswith("first_line\n")

    def test_insert_after_last_line(self, editor, temp_dir):
        """Test inserting after the last line."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        result = editor.invoke("insert:test.py:2:appended")
        assert "after line 2" in result
        content = (temp_dir / "test.py").read_text()
        assert content == "line1\nline2\nappended\n"

    # Delete tests
    def test_delete_lines(self, editor, temp_dir):
        """Test deleting a range of lines."""
        (temp_dir / "test.py").write_text("line1\nline2\nline3\nline4\n")
        result = editor.invoke("delete:test.py:2:3")
        assert "Deleted 2 line(s)" in result
        assert "(2-3)" in result
        content = (temp_dir / "test.py").read_text()
        assert content == "line1\nline4\n"

    def test_delete_single_line(self, editor, temp_dir):
        """Test deleting a single line."""
        (temp_dir / "test.py").write_text("line1\nline2\nline3\n")
        result = editor.invoke("delete:test.py:2:2")
        assert "Deleted 1 line(s)" in result
        content = (temp_dir / "test.py").read_text()
        assert content == "line1\nline3\n"

    def test_delete_all_lines(self, editor, temp_dir):
        """Test deleting all lines from file."""
        (temp_dir / "test.py").write_text("line1\nline2\nline3\n")
        result = editor.invoke("delete:test.py:1:3")
        assert "Deleted 3 line(s)" in result
        content = (temp_dir / "test.py").read_text()
        assert content == ""

    # JSON format tests
    def test_json_format_replace(self, editor, temp_dir):
        """Test JSON format for complex content."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        json_input = '{"op": "replace", "path": "test.py", "start": 1, "end": 2, "content": "new\\ncontent"}'
        result = editor.invoke(json_input)
        assert "Replaced lines" in result
        content = (temp_dir / "test.py").read_text()
        assert "new" in content and "content" in content

    def test_json_format_insert(self, editor, temp_dir):
        """Test JSON format for insert operation."""
        (temp_dir / "test.py").write_text("line1\n")
        json_input = '{"op": "insert", "path": "test.py", "after": 0, "content": "first"}'
        result = editor.invoke(json_input)
        assert "Inserted content" in result
        content = (temp_dir / "test.py").read_text()
        assert content.startswith("first\n")

    def test_json_format_delete(self, editor, temp_dir):
        """Test JSON format for delete operation."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        json_input = '{"op": "delete", "path": "test.py", "start": 1, "end": 1}'
        result = editor.invoke(json_input)
        assert "Deleted" in result
        content = (temp_dir / "test.py").read_text()
        assert content == "line2\n"

    # Validation tests
    def test_path_traversal_prevention(self, editor, temp_dir):
        """Test that path traversal is blocked."""
        result = editor.invoke("replace:../outside.txt:1:1:content")
        assert "Error" in result
        assert "outside" in result.lower() or "root" in result.lower()

    def test_line_bounds_checking(self, editor, temp_dir):
        """Test that out-of-bounds lines are rejected."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        result = editor.invoke("replace:test.py:1:100:content")
        assert "Error" in result
        assert "exceeds" in result.lower() or "bounds" in result.lower()

    def test_start_line_negative(self, editor, temp_dir):
        """Test that negative start line is rejected."""
        # Create the file first
        (temp_dir / "test.py").write_text("line1\n")
        result = editor.invoke("replace:test.py:-1:1:content")
        assert "Error" in result
        assert ">=" in result or "must be >=" in result

    def test_end_line_before_start(self, editor, temp_dir):
        """Test that end < start is rejected."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        result = editor.invoke("replace:test.py:3:2:content")
        assert "Error" in result
        assert ">= start line" in result

    def test_binary_file_rejection(self, editor, temp_dir):
        """Test that binary files are rejected."""
        (temp_dir / "test.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        result = editor.invoke("replace:test.png:1:1:content")
        assert "Error" in result
        assert "binary" in result.lower()

    def test_pyc_file_rejection(self, editor, temp_dir):
        """Test that .pyc files are rejected."""
        (temp_dir / "test.pyc").write_bytes(b"compiled python")
        result = editor.invoke("replace:test.pyc:1:1:content")
        assert "Error" in result
        assert "binary" in result.lower()

    def test_nonexistent_file(self, editor, temp_dir):
        """Test error for non-existent file."""
        result = editor.invoke("replace:nonexistent.py:1:1:content")
        assert "Error" in result
        assert "not found" in result.lower()

    def test_invalid_format(self, editor):
        """Test error for invalid input format."""
        result = editor.invoke("invalid input")
        assert "Error" in result

    def test_unknown_operation(self, editor):
        """Test error for unknown operation."""
        result = editor.invoke("unknown:test.py:1:1:content")
        assert "Error" in result
        assert "unknown" in result.lower()

    def test_invalid_replace_format(self, editor):
        """Test error for incomplete replace format."""
        result = editor.invoke("replace:test.py:1:2")
        assert "Error" in result
        assert "Replace format" in result

    def test_invalid_insert_format(self, editor):
        """Test error for incomplete insert format."""
        result = editor.invoke("insert:test.py:1")
        assert "Error" in result
        assert "Insert format" in result

    def test_invalid_delete_format(self, editor):
        """Test error for incomplete delete format."""
        result = editor.invoke("delete:test.py:1")
        assert "Error" in result
        assert "Delete format" in result

    def test_content_with_newline_escaped(self, editor, temp_dir):
        """Test that \\n escape is properly handled in delimited format."""
        (temp_dir / "test.py").write_text("old\n")
        result = editor.invoke("replace:test.py:1:1:first\\nsecond")
        assert "Replaced lines" in result
        content = (temp_dir / "test.py").read_text()
        assert content == "first\nsecond\n"

    def test_empty_file_replace(self, editor, temp_dir):
        """Test that replace on empty file is handled properly."""
        (temp_dir / "empty.py").write_text("")
        result = editor.invoke("replace:empty.py:1:1:content")
        assert "Error" in result
        assert "exceeds" in result.lower()

    def test_empty_file_insert(self, editor, temp_dir):
        """Test that insert at beginning works on empty file."""
        (temp_dir / "empty.py").write_text("")
        result = editor.invoke("insert:empty.py:0:content")
        assert "Inserted content" in result
        content = (temp_dir / "empty.py").read_text()
        assert content == "content\n"

    def test_insert_before_invalid(self, editor, temp_dir):
        """Test insert before with invalid line number."""
        (temp_dir / "test.py").write_text("line1\n")
        result = editor.invoke("insert:test.py:before_0:content")
        assert "Error" in result
        assert ">=" in result

    def test_insert_after_invalid(self, editor, temp_dir):
        """Test insert after with line number too high."""
        (temp_dir / "test.py").write_text("line1\n")
        result = editor.invoke("insert:test.py:10:content")
        assert "Error" in result
        assert "exceeds" in result.lower()

    def test_invalid_insert_position(self, editor, temp_dir):
        """Test insert with invalid position format."""
        (temp_dir / "test.py").write_text("line1\n")
        result = editor.invoke("insert:test.py:middle:content")
        assert "Error" in result
        assert "Invalid insert position" in result

    def test_edit_adds_newline_if_missing(self, editor, temp_dir):
        """Test that newline is added if content doesn't end with one."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        result = editor.invoke("replace:test.py:2:2:newline")
        assert "Replaced lines" in result
        content = (temp_dir / "test.py").read_text()
        # Should have newline after replacement
        assert content == "line1\nnewline\n"

    def test_replace_preserves_existing_newlines(self, editor, temp_dir):
        """Test that replace with content ending in newline works correctly."""
        (temp_dir / "test.py").write_text("old1\nold2\n")
        result = editor.invoke("replace:test.py:1:1:new1\n")
        assert "Replaced lines" in result
        content = (temp_dir / "test.py").read_text()
        # Should not have double newlines
        assert content == "new1\nold2\n"

    # Search/Replace tests
    def test_search_replace_exact_match(self, editor, temp_dir):
        """Test search_replace with exact text match."""
        (temp_dir / "test.py").write_text('"""A mock weather tool."""\n')
        json_input = (
            '{"op": "search_replace", "path": "test.py", '
            '"old": "A mock weather tool.", "new": "A mock weather tool for testing."}'
        )
        result = editor.invoke(json_input)
        assert "Replaced text" in result
        content = (temp_dir / "test.py").read_text()
        assert "for testing" in content

    def test_search_replace_multiline(self, editor, temp_dir):
        """Test search_replace with multiline content."""
        (temp_dir / "test.py").write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")
        json_input = (
            '{"op": "search_replace", "path": "test.py", '
            '"old": "def foo():\\n    pass", "new": "def foo():\\n    return 42"}'
        )
        result = editor.invoke(json_input)
        assert "Replaced text" in result
        content = (temp_dir / "test.py").read_text()
        assert "return 42" in content
        assert "def bar" in content  # Unchanged

    def test_search_replace_not_found(self, editor, temp_dir):
        """Test search_replace when text is not found."""
        (temp_dir / "test.py").write_text("line1\nline2\n")
        result = editor.invoke(
            '{"op": "search_replace", "path": "test.py", "old": "nonexistent", "new": "replacement"}'
        )
        assert "Error" in result
        assert "not found" in result.lower()

    def test_search_replace_multiple_matches(self, editor, temp_dir):
        """Test search_replace when text appears multiple times."""
        (temp_dir / "test.py").write_text("foo\nbar\nfoo\n")
        result = editor.invoke('{"op": "search_replace", "path": "test.py", "old": "foo", "new": "baz"}')
        assert "Error" in result
        assert "2 occurrences" in result.lower()

    def test_search_replace_similar_text_hint(self, editor, temp_dir):
        """Test search_replace suggests location when text not found but similar exists."""
        (temp_dir / "test.py").write_text("class WeatherTool:\n    pass\n")
        result = editor.invoke('{"op": "search_replace", "path": "test.py", "old": "WeatherTools:", "new": "SkyTool:"}')
        # Should find similar text and suggest location (note: "WeatherTools" vs "WeatherTool")
        assert "Error" in result
        # Should suggest read_file_fragment
        assert "read_file_fragment" in result

    def test_search_replace_preserves_quotes(self, editor, temp_dir):
        """Test that search_replace preserves surrounding content."""
        (temp_dir / "test.py").write_text('    """A mock weather tool."""\n')
        json_input = (
            '{"op": "search_replace", "path": "test.py", '
            '"old": "A mock weather tool.", "new": "A mock weather tool for testing."}'
        )
        result = editor.invoke(json_input)
        assert "Replaced text" in result
        content = (temp_dir / "test.py").read_text()
        # Quotes should be preserved
        assert '"""' in content
        assert "for testing" in content

    def test_search_replace_file_not_found(self, editor, temp_dir):
        """Test search_replace on non-existent file."""
        result = editor.invoke('{"op": "search_replace", "path": "nonexistent.py", "old": "old", "new": "new"}')
        assert "Error" in result
        assert "not found" in result.lower()

    def test_search_replace_empty_old_text(self, editor, temp_dir):
        """Test search_replace with empty old text."""
        (temp_dir / "test.py").write_text("content\n")
        result = editor.invoke('{"op": "search_replace", "path": "test.py", "old": "", "new": "new"}')
        # Empty string matches everywhere, should fail
        assert "Error" in result or "0 occurrences" in result.lower() or "not found" in result.lower()
