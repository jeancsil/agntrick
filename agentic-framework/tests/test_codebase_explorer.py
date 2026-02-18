"""Tests for codebase explorer tools."""

import tempfile
from pathlib import Path

import pytest

from agentic_framework.tools.codebase_explorer import (
    LANGUAGE_EXTENSIONS,
    LANGUAGE_PATTERNS,
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
