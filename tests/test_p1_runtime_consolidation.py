"""
P1E.1: Runtime consolidation regressions.

Freezes contracts for canonical application structure:
- No local environment artifacts tracked
- Backup artifacts outside canonical package
- Single test root
- Clean requirements manifest
- Coherent relative imports
- Core independence from legacy and UI frameworks
- Runtime isolation properties
"""

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Set

import pytest


# ============================================================
# Helpers
# ============================================================

REPO_ROOT = Path(__file__).resolve().parents[1]


def _git_tracked_files() -> Set[str]:
    """
    Get all files tracked by git.
    Returns relative paths from repo root.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
    except Exception as e:
        pytest.fail(f"Cannot run git ls-files: {e}")


def _gitignore_rules() -> tuple[set[str], set[str]]:
    """
    Parse .gitignore into positive and negative rules.
    
    Returns: (positive_rules, negative_rules)
    """
    gitignore_path = REPO_ROOT / ".gitignore"
    if not gitignore_path.exists():
        return set(), set()
    
    positive_rules = set()
    negative_rules = set()
    
    for line in gitignore_path.read_text().split("\n"):
        line = line.strip()
        
        # Ignore empty lines and comments
        if not line or line.startswith("#"):
            continue
        
        # Negative rule (exception)
        if line.startswith("!"):
            negative_rules.add(line[1:])
        else:
            positive_rules.add(line)
    
    return positive_rules, negative_rules


def _read_requirements() -> list[str]:
    """Read requirements.txt lines (non-empty, non-comment)."""
    req_path = REPO_ROOT / "requirements.txt"
    if not req_path.exists():
        return []
    
    lines = []
    for line in req_path.read_text().split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _normalize_package_name(name: str) -> str:
    """Normalize package name for comparison."""
    # Extract package name (before ==, >=, etc.)
    for op in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if op in name:
            name = name.split(op)[0]
    return name.strip().lower().replace("_", "-")


def _find_python_files(directory: Path) -> Set[Path]:
    """Find all .py files in directory."""
    return set(directory.rglob("*.py"))


def _parse_ast_imports(file_path: Path) -> tuple[Set[str], Set[str]]:
    """
    Parse file and extract:
    - absolute imports: (module, names)
    - relative imports: (level, module, names)
    
    Returns: (absolute_imports, relative_imports)
    
    Raises: pytest.fail on parse errors (not silent)
    """
    try:
        content = file_path.read_text()
    except (UnicodeDecodeError, OSError) as e:
        pytest.fail(
            f"Cannot read Python source {file_path.relative_to(REPO_ROOT)}: {e}"
        )
    
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        pytest.fail(
            f"Cannot parse Python source {file_path.relative_to(REPO_ROOT)}: {e}"
        )
    
    absolute_imports = set()
    relative_imports = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                # Absolute import
                if node.module:
                    absolute_imports.add(node.module)
            else:
                # Relative import
                if node.module:
                    relative_imports.add((node.level, node.module))
                else:
                    # from . import ... or from .. import ...
                    relative_imports.add((node.level, ""))
    
    return absolute_imports, relative_imports


def _resolve_relative_import(source_file: Path, level: int, module: str) -> Path | None:
    """
    Resolve a relative import from source_file.
    
    Correct Python semantics:
    - level=1: from .foo → same package
    - level=2: from ..foo → one package up
    - level=3: from ...foo → two packages up
    
    Returns resolved path (either .py or __init__.py), or None if not found.
    """
    # Start from source file's package directory
    current = source_file.parent
    
    # Go up (level - 1) times to find the target package
    for _ in range(max(level - 1, 0)):
        current = current.parent
    
    # Navigate to target module
    if module:
        parts = module.split(".")
        for part in parts:
            current = current / part
    
    # Check for .py file
    py_file = current.with_suffix(".py")
    if py_file.exists():
        return py_file
    
    # Check for __init__.py
    init_file = current / "__init__.py"
    if init_file.exists():
        return init_file
    
    return None


# ============================================================
# Tests: Local Environment & Git
# ============================================================

def test_git_does_not_track_local_environment_or_cache_artifacts():
    """
    P1E.1: Git must not track local environment/cache files.
    
    Forbidden:
    - .env (exact filename)
    - .env.* (except .env.example)
    - __pycache__ (path component)
    - *.pyc, *.pyo
    - .vscode/ (path component)
    - .pytest_cache/ (path component)
    """
    tracked = _git_tracked_files()
    
    violations = []
    
    for path in tracked:
        path_obj = Path(path)
        name = path_obj.name
        parts = path_obj.parts
        
        # Check .env files (permit .env.example)
        if name == ".env":
            violations.append(path)
            continue
        
        if name.startswith(".env."):
            if name != ".env.example":
                violations.append(path)
            continue
        
        # Check path components
        if "__pycache__" in parts:
            violations.append(path)
            continue
        
        if ".vscode" in parts:
            violations.append(path)
            continue
        
        if ".pytest_cache" in parts:
            violations.append(path)
            continue
        
        # Check file suffixes
        if path_obj.suffix in [".pyc", ".pyo"]:
            violations.append(path)
    
    assert not violations, (
        f"Git tracks local artifacts (should be in .gitignore):\n"
        f"{chr(10).join(violations)}"
    )


def test_gitignore_covers_local_runtime_artifacts():
    """
    P1E.1: .gitignore must have explicit positive rules for local artifacts.
    
    Required positive rules (exact set membership):
    - .env
    - .env.*
    - __pycache__/
    - *.pyc
    - .vscode/
    - .pytest_cache/
    - *.db
    - *.sqlite
    - *.sqlite3
    
    Negative rules (exceptions) like !.env.example are separate.
    """
    positive_rules, negative_rules = _gitignore_rules()
    
    required_positive_rules = {
        ".env",
        ".env.*",
        "__pycache__/",
        "*.pyc",
        ".vscode/",
        ".pytest_cache/",
        "*.db",
        "*.sqlite",
        "*.sqlite3",
    }
    
    # Find missing rules using exact set membership
    missing = sorted(required_positive_rules - positive_rules)
    
    assert not missing, (
        f".gitignore missing required positive rules (exact match): {missing}"
    )


def test_git_does_not_track_runtime_databases_or_backups():
    """
    P1E.1: Git must not track databases or backup files.
    
    Forbidden:
    - *.db, *.sqlite, *.sqlite3
    - .aqorath_backups/
    """
    tracked = _git_tracked_files()
    
    violations = []
    for path in tracked:
        if any(path.endswith(ext) for ext in [".db", ".sqlite", ".sqlite3"]):
            violations.append(path)
        elif ".aqorath_backups" in path:
            violations.append(path)
    
    assert not violations, (
        f"Git tracks database/backup files:\n{chr(10).join(violations)}"
    )


# ============================================================
# Tests: Package Structure
# ============================================================

def test_canonical_package_contains_no_source_backup_artifacts():
    """
    P1E.1: aqorath/ must not contain source backup artifacts.
    
    Forbidden:
    - *.bak (exact suffix)
    - *.bak.* (timestamped backups)
    - *.orig
    - *.rej
    - *.patch
    """
    aqorath_dir = REPO_ROOT / "aqorath"
    assert aqorath_dir.is_dir(), (
        "Canonical aqorath/ package must exist"
    )
    
    violations = []
    for file_path in aqorath_dir.rglob("*"):
        if file_path.is_file():
            name = file_path.name
            
            # Check exact suffixes
            if name.endswith(".bak") or name.endswith(".orig") or name.endswith(".rej"):
                violations.append(str(file_path.relative_to(REPO_ROOT)))
                continue
            
            # Check timestamped backups (.bak.YYYYMMDD, .bak.TIMESTAMP, etc.)
            if ".bak." in name:
                violations.append(str(file_path.relative_to(REPO_ROOT)))
                continue
            
            # Check .patch files
            if file_path.suffix == ".patch":
                violations.append(str(file_path.relative_to(REPO_ROOT)))
    
    assert not violations, (
        f"aqorath/ contains backup artifacts (move to archive):\n"
        f"{chr(10).join(violations)}"
    )


def test_only_tests_directory_is_canonical_test_root():
    """
    P1E.1: tests/ must exist as canonical test root.
    
    Contract: tests/ exists and is directory.
              test/ must NOT exist (legacy consolidation).
    """
    tests_dir = REPO_ROOT / "tests"
    legacy_test_dir = REPO_ROOT / "test"
    
    assert tests_dir.is_dir(), (
        "tests/ directory must exist as canonical test root"
    )
    assert not legacy_test_dir.exists(), (
        "Legacy test/ directory must be consolidated into tests/"
    )


# ============================================================
# Tests: Requirements Manifest
# ============================================================

def test_requirements_has_no_placeholder_or_duplicate_entries():
    """
    P1E.1: requirements.txt must not have duplicates or placeholders.
    
    Forbidden:
    - Duplicate package names (normalized)
    - Placeholder entries like "REQ"
    """
    lines = _read_requirements()
    
    seen_packages = {}
    duplicates = []
    placeholders = []
    
    for line in lines:
        normalized = _normalize_package_name(line)
        
        # Check for placeholders
        if normalized in ["req", "todo", "fixme", "xxx"]:
            placeholders.append(line)
        
        # Check for duplicates
        if normalized in seen_packages:
            duplicates.append((normalized, seen_packages[normalized], line))
        else:
            seen_packages[normalized] = line
    
    errors = []
    if duplicates:
        errors.append("Duplicates in requirements.txt:")
        for norm, first, second in duplicates:
            errors.append(f"  {norm}: {first!r} vs {second!r}")
    
    if placeholders:
        errors.append("Placeholder entries in requirements.txt:")
        for ph in placeholders:
            errors.append(f"  {ph!r}")
    
    assert not errors, "\n".join(errors)


# ============================================================
# Tests: Import Coherence
# ============================================================

def test_all_relative_import_targets_inside_aqorath_exist():
    """
    P1E.1: All relative imports within aqorath/ must resolve.
    
    Static AST analysis. No actual imports.
    """
    aqorath_dir = REPO_ROOT / "aqorath"
    assert aqorath_dir.is_dir(), (
        "Canonical aqorath/ package must exist"
    )
    
    py_files = _find_python_files(aqorath_dir)
    
    broken_imports = []
    
    for py_file in py_files:
        _, rel_imports = _parse_ast_imports(py_file)
        
        for level, module in rel_imports:
            # Only check relative imports within aqorath/
            resolved = _resolve_relative_import(py_file, level, module)
            
            if resolved is None:
                broken_imports.append(
                    f"{py_file.relative_to(REPO_ROOT)}: "
                    f"from {'.' * level}{module} import ... (unresolved)"
                )
    
    assert not broken_imports, (
        f"Unresolved relative imports:\n{chr(10).join(broken_imports)}"
    )


def test_canonical_accounting_runtime_does_not_import_legacy_modelos():
    """
    P1E.1: Core accounting modules must not import legacy modelos/ directory.
    
    Core modules:
    - aqorath/core.py
    - aqorath/storage.py
    - aqorath/models.py
    - aqorath/money.py
    - aqorath/catalog.py
    - aqorath/accounting_rules.py
    - aqorath/migrations.py
    - aqorath/config.py
    - aqorath/exercise.py
    - aqorath/templates.py
    """
    core_modules = [
        "core.py",
        "storage.py",
        "models.py",
        "money.py",
        "catalog.py",
        "accounting_rules.py",
        "migrations.py",
        "config.py",
        "exercise.py",
        "templates.py",
    ]
    
    violations = []
    
    for module_name in core_modules:
        module_path = REPO_ROOT / "aqorath" / module_name
        if not module_path.exists():
            continue
        
        abs_imports, _ = _parse_ast_imports(module_path)
        
        for imp in abs_imports:
            if imp.startswith("modelos"):
                violations.append(f"{module_name}: imports {imp}")
    
    assert not violations, (
        f"Core modules importing legacy modelos/:\n{chr(10).join(violations)}"
    )


def test_canonical_accounting_runtime_does_not_import_interface_frameworks():
    """
    P1E.1: Core accounting modules must not import UI frameworks.
    
    Forbidden:
    - PySide6
    - fastapi
    - starlette
    - jinja2
    - weasyprint
    """
    core_modules = [
        "core.py",
        "storage.py",
        "models.py",
        "money.py",
        "catalog.py",
        "accounting_rules.py",
        "migrations.py",
        "config.py",
        "exercise.py",
        "templates.py",
    ]
    
    forbidden_frameworks = {
        "PySide6",
        "fastapi",
        "starlette",
        "jinja2",
        "weasyprint",
    }
    
    violations = []
    
    for module_name in core_modules:
        module_path = REPO_ROOT / "aqorath" / module_name
        if not module_path.exists():
            continue
        
        abs_imports, _ = _parse_ast_imports(module_path)
        
        for imp in abs_imports:
            for fw in forbidden_frameworks:
                if imp.startswith(fw):
                    violations.append(f"{module_name}: imports {imp}")
    
    assert not violations, (
        f"Core modules importing UI frameworks:\n{chr(10).join(violations)}"
    )


# ============================================================
# Tests: Runtime Isolation
# ============================================================

def test_canonical_accounting_runtime_imports_in_clean_subprocess():
    """
    P1E.1: Core runtime can be imported in isolated subprocess.
    
    All core modules must be importable.
    No optional imports with catch-and-ignore.
    """
    repo_root = REPO_ROOT
    
    script = """
import sys
import aqorath
import aqorath.core
import aqorath.models
import aqorath.money
import aqorath.migrations
import aqorath.storage
import aqorath.catalog
import aqorath.accounting_rules
import aqorath.config
import aqorath.exercise
import aqorath.templates
print("OK")
"""
    
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not existing_pythonpath
        else str(repo_root) + os.pathsep + existing_pythonpath
    )
    
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, (
        f"Core runtime subprocess failed:\n{result.stderr}"
    )


def test_importing_package_does_not_eagerly_load_interface_frameworks():
    """
    P1E.1: import aqorath must not preload UI frameworks.
    """
    repo_root = REPO_ROOT
    
    script = """
import sys
import aqorath

forbidden = {"PySide6", "fastapi", "starlette"}
loaded = {m for m in sys.modules if any(m.startswith(fw) for fw in forbidden)}

if loaded:
    print(f"FAIL: {loaded}")
    sys.exit(1)
print("OK")
"""
    
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not existing_pythonpath
        else str(repo_root) + os.pathsep + existing_pythonpath
    )
    
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, (
        f"Package eagerly loads interfaces:\n{result.stdout}"
    )


# ============================================================
# Tests: Python Artifact Tracking
# ============================================================

def test_git_does_not_track_generated_python_backup_files():
    """
    P1E.1: Git must not track Python generated/backup files.
    
    Forbidden:
    - *.pyc
    - *.pyo
    - any path containing __pycache__ component
    - any filename ending with .bak, .bak.*, .orig, .rej
    """
    tracked = _git_tracked_files()
    
    violations = []
    for path in tracked:
        path_obj = Path(path)
        
        # Check suffixes
        if path_obj.suffix in [".pyc", ".pyo"]:
            violations.append(path)
            continue
        
        # Check for __pycache__ component
        if "__pycache__" in path_obj.parts:
            violations.append(path)
            continue
        
        # Check for backup suffixes (exact match)
        if path_obj.name.endswith(".bak") or path_obj.name.endswith(".orig") or path_obj.name.endswith(".rej"):
            violations.append(path)
            continue
        
        # Check for .bak.* pattern
        if ".bak." in path_obj.name:
            violations.append(path)
    
    assert not violations, (
        f"Git tracks Python backup/generated files:\n{chr(10).join(violations)}"
    )
