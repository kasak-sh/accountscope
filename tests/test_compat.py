"""The package must parse and compile on the oldest Python it claims to support (3.10),
and must never import a networking module."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "accountscope"
MODULES = sorted(PACKAGE.rglob("*.py"))
FORBIDDEN_IMPORTS = {"socket", "urllib", "http", "ssl", "smtplib"}
CANDIDATE_INTERPRETERS = ("python3.10", "python3.11", "/usr/bin/python3")


def _version(interpreter: str) -> tuple[int, int] | None:
    try:
        proc = subprocess.run([interpreter, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        major, minor = proc.stdout.split()
        return int(major), int(minor)
    except ValueError:
        return None


def oldest_interpreter() -> tuple[str, tuple[int, int]] | None:
    found = [(name, v) for name in CANDIDATE_INTERPRETERS if (v := _version(name)) is not None]
    if not found:
        return None
    return min(found, key=lambda pair: pair[1])


def test_modules_exist():
    assert MODULES, "no modules found under accountscope/"


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_module_parses_under_python_3_10(module: Path):
    source = module.read_text(encoding="utf-8")
    ast.parse(source, filename=str(module), feature_version=(3, 10))


def test_modules_compile_on_the_oldest_available_interpreter():
    chosen = oldest_interpreter()
    if chosen is None:
        pytest.skip(f"none of {', '.join(CANDIDATE_INTERPRETERS)} is available to compile against")
    interpreter, version = chosen
    failures = []
    for module in MODULES:
        proc = subprocess.run([interpreter, "-m", "py_compile", str(module)], capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(f"{module.name} ({proc.stderr.strip() or proc.stdout.strip()})")
    assert not failures, f"{interpreter} {version[0]}.{version[1]} could not compile: " + "; ".join(failures)


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_no_networking_imports(module: Path):
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    offenders = sorted({n for n in names if n.split(".")[0] in FORBIDDEN_IMPORTS})
    assert not offenders, f"{module.name} imports {offenders}; accountscope opens no network connection"


def test_this_interpreter_is_supported():
    assert sys.version_info >= (3, 10)
