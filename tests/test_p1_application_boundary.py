"""
P1E.3A Application Boundary Architecture Contracts

Tests to enforce final consolidation of Aqorath architecture:
- Single application runtime via aqorath.application
- Clean separation of core/storage/domain from UI/persistence
- Retirement of legacy prototypes and orchestrators
- No dependencies on legacy modelos/ package
"""
import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]


def _git_tracked_files() -> set[str]:
    """Retrieve tracked files from git ls-files."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()


def _find_python_files(directory: Path) -> list[Path]:
    """Recursively find *.py files in directory."""
    return sorted(directory.glob("**/*.py"))


def _parse_ast_imports(file_path: Path) -> Tuple[Set[str], Set[Tuple[int, str, str]]]:
    """
    Parse file and extract imports robustly.
    Returns: (absolute_imports, from_imports_with_names)

    absolute_imports: Set of module names from "import X"
    from_imports_with_names: Set of (level, module, imported_name) tuples:
      - level: 0 for absolute, 1+ for relative (.., .., etc.)
      - module: module name or empty string for "from . import X"
      - imported_name: the actual name being imported (alias.name, NOT alias.asname)

    IMPORTANT: imported_name is what was IMPORTED, not the local binding.
    Example: from aqorath import application as app
    Result: (0, "aqorath", "application") — captures "application", not "app"

    Examples:
      from aqorath import application → (0, "aqorath", "application")
      from aqorath import application as app → (0, "aqorath", "application")
      from aqorath.application import foo → (0, "aqorath.application", "foo")
      from . import application → (1, "", "application")
      from . import application as app → (1, "", "application")
      from .application import foo → (1, "application", "foo")
      from .. import core → (2, "", "core")
      from ..core import post_entry → (2, "core", "post_entry")
    """
    try:
        content = file_path.read_text()
    except (UnicodeDecodeError, OSError) as e:
        raise RuntimeError(f"Cannot read {file_path}: {e}")

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        raise RuntimeError(f"Cannot parse {file_path}: {e}")

    absolute_imports = set()
    from_imports_with_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # Capture each imported name with full context
            # Use alias.name (what was imported), NOT alias.asname (local binding)
            for alias in node.names:
                from_imports_with_names.add(
                    (node.level, node.module or "", alias.name)
                )

    return absolute_imports, from_imports_with_names


def _imports_module_family(imports: Set[str], module: str) -> bool:
    """
    Check if imports contains module or any submodule of module.

    Examples:
    - _imports_module_family({"modelos.libro", "modelos.cfdi"}, "modelos") -> True
    - _imports_module_family({"fastapi.responses"}, "fastapi") -> True
    - _imports_module_family({"sqlalchemy.orm"}, "sqlalchemy") -> True
    """
    return any(
        imported == module or imported.startswith(module + ".")
        for imported in imports
    )


def _detects_application_import(
    abs_imports: Set[str], from_imports: Set[Tuple[int, str, str]]
) -> bool:
    """
    Check if imports detect aqorath.application in any form, with precision.

    Detects:
      - import aqorath.application
      - import aqorath.application.foo
      - from aqorath import application
      - from aqorath import application as app (name="application", not asname)
      - from aqorath.application import foo
      - from . import application
      - from . import application as app (name="application")
      - from .application import foo
      - from .. import application

    Does NOT falsely detect:
      - from aqorath import application_config
      - from aqorath import application_helpers
      - from . import application_helpers
      - from . import application_config as app
      - from .helpers import application (module is "helpers", not "application")
      - from . import app_config (not exact name "application")
    """
    # Absolute forms: import aqorath.application or aqorath.application.submodule
    if _imports_module_family(abs_imports, "aqorath.application"):
        return True

    # from X import Y forms: check exact name match or family
    for level, module, name in from_imports:
        if level == 0:
            # Absolute from imports
            if module == "aqorath" and name == "application":
                return True
            if _imports_module_family({module}, "aqorath.application"):
                return True
        else:
            # Relative from imports: from . import X or from .X import Y
            # Only detect if module is "application" family or empty with exact name
            if not module and name == "application":
                # from . import application or from .. import application
                return True
            if _imports_module_family({module}, "application"):
                # from .application import foo or from ..application import foo
                return True

    return False


def _detects_core_import(
    abs_imports: Set[str], from_imports: Set[Tuple[int, str, str]]
) -> bool:
    """
    Check if imports detect aqorath.core in any form, with precision.

    Detects:
      - import aqorath.core
      - import aqorath.core.foo
      - from aqorath import core
      - from aqorath import core as c (name="core", not asname)
      - from aqorath.core import post_entry
      - from . import core
      - from . import core as c (name="core")
      - from .core import foo

    Does NOT falsely detect:
      - from aqorath import core_helpers
      - from . import core_utils
      - from . import core_config as c
      - from .helpers import core (module is "helpers", not "core")
      - from . import c_utils (not exact name "core")
    """
    # Absolute forms: import aqorath.core or aqorath.core.submodule
    if _imports_module_family(abs_imports, "aqorath.core"):
        return True

    # from X import Y forms: check exact name match or family
    for level, module, name in from_imports:
        if level == 0:
            # Absolute from imports
            if module == "aqorath" and name == "core":
                return True
            if _imports_module_family({module}, "aqorath.core"):
                return True
        else:
            # Relative from imports: from . import X or from .X import Y
            # Only detect if module is "core" family or empty with exact name
            if not module and name == "core":
                # from . import core or from .. import core
                return True
            if _imports_module_family({module}, "core"):
                # from .core import foo or from ..core import foo
                return True

    return False


def _parse_import_snippet(tmp_path: Path, source: str) -> tuple:
    """
    Parse a Python import snippet by writing it to a temp file and parsing it.
    Returns: (absolute_imports, from_imports_with_names)

    This ensures regressions traverse the full pipeline: source → file → parser → detection.
    """
    snippet_file = tmp_path / "snippet.py"
    snippet_file.write_text(source)
    return _parse_ast_imports(snippet_file)


def _verify_import_regressions(tmp_path: Path):
    """
    End-to-end regression tests for import detection.
    Parses real Python source snippets through _parse_ast_imports().

    12 cases: 6 application + 6 core

    APPLICATION:
    1. from aqorath import application as app → DETECT
    2. from aqorath import application_config as app → NO DETECT
    3. from . import application as app → DETECT
    4. from .helpers import application → NO DETECT
    5. from .application import foo as bar → DETECT
    6. from .application_helpers import foo → NO DETECT

    CORE:
    7. from aqorath import core as c → DETECT
    8. from aqorath import core_helpers as c → NO DETECT
    9. from . import core as c → DETECT
    10. from .helpers import core → NO DETECT
    11. from .core import foo as bar → DETECT
    12. from .core_utils import foo → NO DETECT
    """
    # APPLICATION TEST CASES

    # Case 1: from aqorath import application as app (with alias) → DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from aqorath import application as app")
    assert _detects_application_import(abs_imports, from_imports), (
        "REGRESSION 1: from aqorath import application as app must detect"
    )

    # Case 2: from aqorath import application_config as app → NO DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from aqorath import application_config as app")
    assert not _detects_application_import(abs_imports, from_imports), (
        "REGRESSION 2: from aqorath import application_config must NOT detect"
    )

    # Case 3: from . import application as app (with alias) → DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from . import application as app")
    assert _detects_application_import(abs_imports, from_imports), (
        "REGRESSION 3: from . import application as app must detect"
    )

    # Case 4: from .helpers import application → NO DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from .helpers import application")
    assert not _detects_application_import(abs_imports, from_imports), (
        "REGRESSION 4: from .helpers import application must NOT detect"
    )

    # Case 5: from .application import foo as bar (with alias) → DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from .application import foo as bar")
    assert _detects_application_import(abs_imports, from_imports), (
        "REGRESSION 5: from .application import foo as bar must detect"
    )

    # Case 6: from .application_helpers import foo → NO DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from .application_helpers import foo")
    assert not _detects_application_import(abs_imports, from_imports), (
        "REGRESSION 6: from .application_helpers import foo must NOT detect"
    )

    # CORE TEST CASES

    # Case 7: from aqorath import core as c (with alias) → DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from aqorath import core as c")
    assert _detects_core_import(abs_imports, from_imports), (
        "REGRESSION 7: from aqorath import core as c must detect"
    )

    # Case 8: from aqorath import core_helpers as c → NO DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from aqorath import core_helpers as c")
    assert not _detects_core_import(abs_imports, from_imports), (
        "REGRESSION 8: from aqorath import core_helpers must NOT detect"
    )

    # Case 9: from . import core as c (with alias) → DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from . import core as c")
    assert _detects_core_import(abs_imports, from_imports), (
        "REGRESSION 9: from . import core as c must detect"
    )

    # Case 10: from .helpers import core → NO DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from .helpers import core")
    assert not _detects_core_import(abs_imports, from_imports), (
        "REGRESSION 10: from .helpers import core must NOT detect"
    )

    # Case 11: from .core import foo as bar (with alias) → DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from .core import foo as bar")
    assert _detects_core_import(abs_imports, from_imports), (
        "REGRESSION 11: from .core import foo as bar must detect"
    )

    # Case 12: from .core_utils import foo → NO DETECT
    abs_imports, from_imports = _parse_import_snippet(tmp_path, "from .core_utils import foo")
    assert not _detects_core_import(abs_imports, from_imports), (
        "REGRESSION 12: from .core_utils import foo must NOT detect"
    )



# ==============================================================================
# APPLICATION BOUNDARY EXISTENCE
# ==============================================================================

def test_canonical_application_boundary_exists():
    """
    P1E.3A: Application boundary must exist as aqorath/application.py.

    Future entrypoints (web, desktop, CLI) will import from this module,
    not from root or other locations.
    """
    application_py = REPO_ROOT / "aqorath" / "application.py"
    assert application_py.exists() and application_py.is_file(), (
        "aqorath/application.py must exist as canonical application boundary"
    )


def test_canonical_application_boundary_imports_cleanly():
    """
    P1E.3A: Application boundary module must be importable in isolation.

    Uses subprocess to ensure clean import without side effects.
    Preserves system environment and adds repo root to PYTHONPATH.
    """
    script = """
import sys
import aqorath
import aqorath.application
print("OK")
"""
    repo_root = REPO_ROOT
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
        f"aqorath.application import failed:\n{result.stderr}"
    )


def test_application_boundary_exposes_minimal_public_api():
    """
    P1E.3A: Application boundary must expose canonical public API.

    These four functions are the sole entry points for all adapters:
    - list_templates(): enumerate contable templates
    - preview_template(...): preview accounting without persistence
    - post_template(...): persist via canonical authority (SQLite)
    - get_trial_balance(...): query consolidated balances
    """
    import aqorath.application

    required_callables = {
        "list_templates",
        "preview_template",
        "post_template",
        "get_trial_balance",
    }

    found = {
        name for name in dir(aqorath.application)
        if callable(getattr(aqorath.application, name, None))
        and not name.startswith("_")
    }

    missing = required_callables - found
    assert not missing, (
        f"aqorath.application missing required callables: {missing}"
    )


def test_application_boundary_delegates_to_core(monkeypatch):
    """
    P1E.3A: Application boundary is a facade, not a second motor.

    Application methods must delegate to core, not duplicate logic.
    Uses monkeypatch to verify delegation with unique sentinels and full arg propagation.
    """
    import aqorath.application
    import aqorath.core

    # Verify application exposes _core attribute pointing to aqorath.core
    assert hasattr(aqorath.application, "_core"), (
        "aqorath.application must expose aqorath.core as _core"
    )
    assert aqorath.application._core is aqorath.core, (
        "aqorath.application._core must be aqorath.core"
    )

    # Create unique sentinel objects for each return value
    sentinel_list = object()
    sentinel_preview = object()
    sentinel_post = object()
    sentinel_balance = object()

    # Create mock core functions to verify delegation
    call_log = {}

    def mock_list_templates():
        call_log["list_templates_called"] = True
        return sentinel_list

    def mock_generate_preview(template_key, amount, ctx=None):
        call_log["preview_args"] = (template_key, amount, ctx)
        return sentinel_preview

    def mock_post_entry(template_key_or_entry, amount=None, ctx=None, user=None):
        call_log["post_args"] = (template_key_or_entry, amount, ctx, user)
        return sentinel_post

    def mock_trial_balance(as_of=None):
        call_log["balance_arg"] = as_of
        return sentinel_balance

    # Monkeypatch core functions
    monkeypatch.setattr(aqorath.core, "list_templates", mock_list_templates)
    monkeypatch.setattr(aqorath.core, "generate_preview", mock_generate_preview)
    monkeypatch.setattr(aqorath.core, "post_entry", mock_post_entry)
    monkeypatch.setattr(aqorath.core, "trial_balance", mock_trial_balance)

    # Verify application delegates to these with correct return propagation
    result1 = aqorath.application.list_templates()
    assert "list_templates_called" in call_log, "list_templates not delegated"
    assert result1 is sentinel_list, "list_templates return not propagated"

    result2 = aqorath.application.preview_template("t1", 100, ctx="ctx1")
    assert "preview_args" in call_log, "preview_template not delegated"
    assert call_log["preview_args"] == ("t1", 100, "ctx1"), "preview_template args not propagated correctly"
    assert result2 is sentinel_preview, "preview_template return not propagated"

    result3 = aqorath.application.post_template("t2", amount=200, ctx={"key": "val"}, user="u1")
    assert "post_args" in call_log, "post_template not delegated"
    assert call_log["post_args"] == ("t2", 200, {"key": "val"}, "u1"), "post_template args not propagated correctly"
    assert result3 is sentinel_post, "post_template return not propagated"

    result4 = aqorath.application.get_trial_balance(as_of="2026-01-01")
    assert "balance_arg" in call_log, "get_trial_balance not delegated"
    assert call_log["balance_arg"] == "2026-01-01", "get_trial_balance arg not propagated"
    assert result4 is sentinel_balance, "get_trial_balance return not propagated"


def test_application_boundary_is_interface_agnostic():
    """
    P1E.3A: Application boundary must not import UI/reporting frameworks.

    Forbidden: FastAPI, PySide6, Jinja2, WeasyPrint, tkinter, etc.
    The application layer is not tied to any specific interface technology.

    Uses family matching to detect framework.responses, pydantic.v1, etc.
    """
    app_py = REPO_ROOT / "aqorath" / "application.py"
    if not app_py.exists():
        raise AssertionError("aqorath/application.py does not exist")

    abs_imports, from_imports = _parse_ast_imports(app_py)

    forbidden_frameworks = {
        "fastapi", "starlette", "pydantic",
        "PySide6", "PyQt5", "PyQt6",
        "jinja2", "weasyprint",
        "tkinter", "flask", "django",
        "textual", "streamlit",
        "modelos",
    }

    # Extract all imported modules from from_imports for checking
    from_import_modules = {module for level, module, name in from_imports if module}

    violations = []
    for framework in forbidden_frameworks:
        if _imports_module_family(abs_imports, framework) or \
           _imports_module_family(from_import_modules, framework):
            violations.append(framework)

    assert not violations, (
        f"aqorath/application imports forbidden frameworks: {violations}"
    )


def test_application_boundary_does_not_own_storage_or_schema():
    """
    P1E.3A: Application boundary must not directly open storage.

    Persistence is delegated to core/storage, not replicated in application.
    Forbidden direct storage imports: sqlite3, sqlalchemy, sqlmodel, pandas, openpyxl.

    Uses family matching to detect sqlalchemy.orm, pandas.core, openpyxl.workbook, etc.
    """
    app_py = REPO_ROOT / "aqorath" / "application.py"
    if not app_py.exists():
        raise AssertionError("aqorath/application.py does not exist")

    abs_imports, from_imports = _parse_ast_imports(app_py)

    forbidden_storage = {
        "sqlite3", "sqlalchemy", "sqlmodel",
        "pandas", "openpyxl",
    }

    # Extract all imported modules from from_imports for checking
    from_import_modules = {module for level, module, name in from_imports if module}

    violations = []
    for storage in forbidden_storage:
        if _imports_module_family(abs_imports, storage) or \
           _imports_module_family(from_import_modules, storage):
            violations.append(storage)

    assert not violations, (
        f"aqorath/application directly imports storage/persistence: {violations}"
    )


# ==============================================================================
# LEGACY PACKAGE RETIREMENT
# ==============================================================================

def test_legacy_modelos_package_is_retired():
    """
    P1E.3A: Legacy modelos/ package must be completely retired.

    Phase 1E.2 removed runtime dependencies on it.
    Phase 1E.3 removes it from the repository surface.
    Git history and documentation preserve historical intent.
    """
    modelos_dir = REPO_ROOT / "modelos"
    assert not modelos_dir.exists(), (
        "Legacy modelos/ package must be retired from repository"
    )


# ==============================================================================
# ROOT LEGACY ORCHESTRATORS ABSENT
# ==============================================================================

def test_legacy_root_application_orchestrators_are_absent():
    """
    P1E.3A: Legacy root application orchestrators must be absent.

    Forbidden:
    - app.py (Libro/XLSX frontend)
    - name-app.py (legacy named entry point)

    These were prototypes of a secondary motor, not the canonical application.
    """
    tracked = _git_tracked_files()

    forbidden = {"app.py", "name-app.py"}
    found = forbidden & tracked

    assert not found, (
        f"Legacy root orchestrators must be absent: {found}"
    )


# ==============================================================================
# PROTOTYPE API/UI ABSENCE
# ==============================================================================

def test_prototype_api_entrypoints_are_absent():
    """
    P1E.3A: Prototype API entrypoints must be absent.

    Forbidden:
    - api.py (root)
    - api/ (root package)

    Future APIs will be adapters over aqorath.application, not direct FastAPI.
    """
    tracked = _git_tracked_files()

    # Check for api.py in root
    assert "api.py" not in tracked, (
        "Prototype api.py must be absent"
    )

    # Check for api/* (package)
    api_files = {p for p in tracked if p.startswith("api/")}
    assert not api_files, (
        f"Prototype api/ package must be absent: {api_files}"
    )


def test_prototype_desktop_runtime_is_absent():
    """
    P1E.3A: Prototype desktop UI runtime must be absent.

    Forbidden:
    - aqorath/ui/ (skeletal PySide6 UI)
    - scripts/launch_ui.py

    The current UI is not integrated with the application layer.
    Future desktop adapter will be designed properly.
    """
    tracked = _git_tracked_files()

    # Check for aqorath/ui/*
    ui_files = {p for p in tracked if p.startswith("aqorath/ui/")}
    assert not ui_files, (
        f"Prototype aqorath/ui/ must be absent: {ui_files}"
    )

    # Check for launch_ui.py
    assert "scripts/launch_ui.py" not in tracked, (
        "Prototype scripts/launch_ui.py must be absent"
    )


def test_legacy_company_models_are_absent():
    """
    P1E.3A: Legacy Company model duplicates must be absent.

    Forbidden:
    - company.py (root)
    - aqorath/company.py

    Both are prototype SQLModel Company definitions outside the canonical
    aqorath.models schema. Phase 1E.3 retires both rather than canonizing
    either. Future entity identity will be designed explicitly in a later
    product phase.
    """
    tracked = _git_tracked_files()

    forbidden = {"company.py", "aqorath/company.py"}
    found = forbidden & tracked

    assert not found, (
        f"Legacy Company model duplicates must be absent: {found}"
    )


def test_legacy_reporting_entrypoint_is_absent():
    """
    P1E.3A: Legacy reporting entrypoint must be absent.

    Forbidden:
    - reports_jinja.py (root)
    - scripts/init_and_pdf_example.py

    Reporting will be a future Document Factory adapter, not a root module.
    """
    tracked = _git_tracked_files()

    forbidden = {"reports_jinja.py", "scripts/init_and_pdf_example.py"}
    found = forbidden & tracked

    assert not found, (
        f"Legacy reporting entrypoint must be absent: {found}"
    )


def test_legacy_main_cli_and_packaging_are_absent():
    """
    P1E.3A: Legacy main CLI and packaging must be absent.

    Forbidden:
    - main.py (root CLI orchestrator)
    - main.spec (PyInstaller spec)
    - scripts/build_executable.sh
    - scripts/build_executable_windows.bat

    main.py wraps XSD/CFDI tooling, not the canonical accounting application.
    No packaging until application layer is approved.
    """
    tracked = _git_tracked_files()

    forbidden = {
        "main.py",
        "main.spec",
        "scripts/build_executable.sh",
        "scripts/build_executable_windows.bat",
    }
    found = forbidden & tracked

    assert not found, (
        f"Legacy main CLI and packaging must be absent: {found}"
    )


# ==============================================================================
# RUNTIME IMPORT HYGIENE
# ==============================================================================

def test_no_runtime_python_outside_legacy_tree_imports_modelos():
    """
    P1E.3A: No production runtime code outside modelos/ imports modelos/.

    Checks all tracked *.py files (excluding modelos/, docs/, tests/).
    Must not contain: import modelos / from modelos import ...

    Uses family matching to detect modelos.libro, modelos.cfdi, etc.
    Parse errors are NOT silenced; they are assertion failures.
    """
    tracked = _git_tracked_files()

    violations = []
    parse_errors = []

    for path in tracked:
        # Skip modelos/, docs/, tests/
        if path.startswith(("modelos/", "docs/", "tests/")):
            continue

        if not path.endswith(".py"):
            continue

        try:
            abs_imports, from_imports = _parse_ast_imports(REPO_ROOT / path)
        except RuntimeError as e:
            # Parse errors are NOT silenced; they indicate code problems
            parse_errors.append(f"{path}: {e}")
            continue

        # Extract all imported modules from from_imports
        from_import_modules = {module for level, module, name in from_imports if module}

        # Check for modelos imports using family matching
        if _imports_module_family(abs_imports, "modelos") or \
           _imports_module_family(from_import_modules, "modelos"):
            violations.append(path)

    assert not parse_errors, (
        f"Parse errors in tracked Python files:\n" + "\n".join(parse_errors)
    )
    assert not violations, (
        f"Runtime Python imports legacy modelos/:\n" + "\n".join(violations)
    )


# ==============================================================================
# ADAPTER LAYER CONTRACTS (FUTURE)
# ==============================================================================

def test_future_adapters_must_not_import_core_directly(tmp_path):
    """
    P1E.3A: Future adapters must import via aqorath.application, not core.

    Contract: if aqorath/adapters/ exists, code there must not directly
    import aqorath.core. Must use aqorath.application as facade.

    Regression tests embedded: verifies alias handling and relative import precision.
    Currently: PASS (adapters/ does not exist yet).
    """
    # Verify import detection regressions
    _verify_import_regressions(tmp_path)

    adapters_dir = REPO_ROOT / "aqorath" / "adapters"
    if not adapters_dir.exists():
        # No adapters yet, contract satisfied
        return

    adapter_files = _find_python_files(adapters_dir)
    violations = []

    for py_file in adapter_files:
        try:
            abs_imports, from_imports = _parse_ast_imports(py_file)
        except RuntimeError as e:
            raise AssertionError(f"Cannot parse adapter {py_file}: {e}")

        if _detects_core_import(abs_imports, from_imports):
            violations.append(str(py_file.relative_to(REPO_ROOT)))

    assert not violations, (
        f"Adapters import aqorath.core directly (use aqorath.application): {violations}"
    )


# ==============================================================================
# CORE/DOMAIN INDEPENDENCE
# ==============================================================================

def test_core_does_not_depend_on_application_boundary(tmp_path):
    """
    P1E.3A: Core must not depend on application boundary layer.

    Dependency direction: adapter → application → core (never upward).
    Detects all forms: absolute imports, from imports, relative imports.

    Regression tests embedded: verifies alias handling and relative import precision.
    """
    # Verify import detection regressions before checking core modules
    _verify_import_regressions(tmp_path)

    core_py = REPO_ROOT / "aqorath" / "core.py"
    if not core_py.exists():
        raise AssertionError("aqorath/core.py does not exist")

    try:
        abs_imports, from_imports = _parse_ast_imports(core_py)
    except RuntimeError as e:
        raise AssertionError(f"Cannot parse core.py: {e}")

    assert not _detects_application_import(abs_imports, from_imports), (
        "aqorath/core.py must not depend on aqorath.application"
    )


def test_domain_and_storage_do_not_depend_on_application(tmp_path):
    """
    P1E.3A: Domain/storage layer must not depend on application.

    Core layer independence requires: no imports of aqorath.application
    from any of: core, storage, models, money, catalog, accounting_rules,
    migrations, config, exercise, templates.

    Detects all forms: absolute imports, from imports, relative imports.
    Regression tests embedded: verifies alias handling and relative import precision.
    """
    # Verify import detection regressions
    _verify_import_regressions(tmp_path)

    core_modules = [
        "core.py", "storage.py", "models.py", "money.py", "catalog.py",
        "accounting_rules.py", "migrations.py", "config.py", "exercise.py",
        "templates.py",
    ]

    violations = []
    for module_name in core_modules:
        module_py = REPO_ROOT / "aqorath" / module_name
        if not module_py.exists():
            continue

        try:
            abs_imports, from_imports = _parse_ast_imports(module_py)
        except RuntimeError as e:
            raise AssertionError(f"Cannot parse {module_name}: {e}")

        if _detects_application_import(abs_imports, from_imports):
            violations.append(module_name)

    assert not violations, (
        f"Core/storage modules depend on application layer: {violations}"
    )


# ==============================================================================
# MAINTENANCE SCRIPTS
# ==============================================================================

def test_maintenance_scripts_do_not_define_application_authority():
    """
    P1E.3A: Maintenance scripts are tools, not the application.

    Checks scripts/*.py that survive:
    - Must not import modelos/ or submodules (legacy)
    - Must not define top-level classes App/Application/AqorathApplication
    """
    scripts_dir = REPO_ROOT / "scripts"
    if not scripts_dir.exists():
        return

    script_files = _find_python_files(scripts_dir)
    violations = []

    for script_py in script_files:
        try:
            abs_imports, from_imports = _parse_ast_imports(script_py)
        except RuntimeError as e:
            raise AssertionError(f"Cannot parse script {script_py.name}: {e}")

        # Extract all imported modules from from_imports
        from_import_modules = {module for level, module, name in from_imports if module}

        # Check for modelos imports using family matching
        if _imports_module_family(abs_imports, "modelos") or \
           _imports_module_family(from_import_modules, "modelos"):
            violations.append(f"{script_py.name}: imports modelos")

        # Check for application-defining classes (top-level only)
        try:
            content = script_py.read_text()
            tree = ast.parse(content)
            # Only inspect top-level nodes (tree.body)
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    if node.name in ("App", "Application", "AqorathApplication"):
                        violations.append(
                            f"{script_py.name}: defines {node.name} class at top-level"
                        )
        except SyntaxError as e:
            raise AssertionError(f"Syntax error in {script_py.name}: {e}")

    assert not violations, (
        f"Maintenance scripts overreach application authority: {violations}"
    )
