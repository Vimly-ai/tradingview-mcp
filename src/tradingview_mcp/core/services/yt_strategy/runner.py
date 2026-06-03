"""Sandboxed exec of LLM-generated strategy code.

This file is security-critical. Modifications must add a regression test
to test_runner_sandbox.py first.

Defense in depth:
    1. AST pre-scan (this file): reject before exec on forbidden names
    2. Restricted exec namespace: only safe libraries in scope
    3. Subprocess isolation: strategy runs in a separate Process
    4. Wall-clock timeout: process.kill() after N seconds
    5. Memory cap: RLIMIT_AS in subprocess

Layers 2-5 are implemented in the next task; layer 1 is here.
"""
from __future__ import annotations

import ast


class SecurityViolation(Exception):
    """Raised when AST scan rejects LLM-generated code."""

    def __init__(self, message: str, line: int | None = None, snippet: str | None = None):
        super().__init__(message)
        self.line = line
        self.snippet = snippet


_BANNED_MODULES = frozenset({
    "os", "subprocess", "socket", "urllib", "urllib2", "urllib3",
    "requests", "httpx", "aiohttp", "ftplib", "smtplib", "telnetlib",
    "shutil", "glob", "pickle", "marshal", "shelve", "dbm",
    "ctypes", "multiprocessing", "threading", "asyncio",
    "signal", "atexit", "resource", "tempfile", "pathlib",
    "importlib", "imp", "pty", "fcntl", "ioctl",
    "platform", "sysconfig", "site", "code", "codeop",
    "builtins",  # full reflective access to all dangerous builtins
})

_BANNED_BUILTINS = frozenset({
    "open", "eval", "exec", "compile", "__import__",
    "globals", "locals", "vars", "breakpoint",
    "exit", "quit", "help", "input",
    "__builtins__",   # also catch bare-name access
})

_BANNED_DUNDER_ATTRS = frozenset({
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__builtins__", "__code__",
    "__import__", "__loader__", "__spec__",
    # __dict__ allowed only on self.data - handled separately
})


def _line_snippet(code: str, line: int | None) -> str | None:
    if line is None:
        return None
    lines = code.splitlines()
    if 0 < line <= len(lines):
        return lines[line - 1]
    return None


class _ScanVisitor(ast.NodeVisitor):
    def __init__(self, code: str) -> None:
        self.code = code
        self.violations: list[SecurityViolation] = []

    def _fail(self, msg: str, node: ast.AST) -> None:
        line = getattr(node, "lineno", None)
        self.violations.append(SecurityViolation(msg, line=line, snippet=_line_snippet(self.code, line)))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            if top in _BANNED_MODULES:
                self._fail(f"Forbidden import: {alias.name!r} (banned module {top!r}).", node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top = node.module.split(".", 1)[0]
            if top in _BANNED_MODULES:
                self._fail(f"Forbidden import: from {node.module!r} (banned module {top!r}).", node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in _BANNED_BUILTINS:
            self._fail(f"Forbidden builtin: {node.id!r}.", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _BANNED_DUNDER_ATTRS:
            self._fail(f"Forbidden attribute access: {node.attr!r}.", node)
        elif node.attr == "__dict__":
            # Allowed only on self.data
            v = node.value
            if not (isinstance(v, ast.Attribute) and v.attr == "data"
                    and isinstance(v.value, ast.Name) and v.value.id == "self"):
                self._fail("Forbidden attribute access: '__dict__' allowed only on self.data.", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # getattr/setattr/delattr/hasattr with dunder string -> reject
        func = node.func
        is_reflective = (
            isinstance(func, ast.Name)
            and func.id in {"getattr", "setattr", "delattr", "hasattr"}
        )
        if is_reflective and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            arg = node.args[1].value
            if isinstance(arg, str) and arg.startswith("__"):
                self._fail(
                    f"Forbidden reflective access: {func.id}(_, {arg!r}).", node,
                )
        self.generic_visit(node)


def scan_strategy_code(code: str) -> None:
    """Reject LLM-generated *code* if it references forbidden names.

    Raises:
        SecurityViolation: on first forbidden reference encountered. The
            exception's ``line`` and ``snippet`` attributes locate it.
        SyntaxError: if *code* is not parseable Python.
    """
    tree = ast.parse(code)
    visitor = _ScanVisitor(code)
    visitor.visit(tree)
    if visitor.violations:
        raise visitor.violations[0]
