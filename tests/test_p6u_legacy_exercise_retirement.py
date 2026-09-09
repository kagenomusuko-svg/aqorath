"""Phase 6U.2 — legacy exercise closing must remain importable but non-persistent."""

import ast
from pathlib import Path


def test_legacy_exercise_surface_is_fail_closed():
    import aqorath.exercise as exercise

    result = exercise.close_exercise()

    assert result == {
        "ok": False,
        "code": exercise.LEGACY_EXERCISE_RETIRED,
        "error": (
            "Legacy exercise closing is retired because it bypassed canonical ledger "
            "persistence. Use the governed Aqorath closing workflow when available."
        ),
    }


def test_legacy_exercise_module_contains_no_parallel_persistence_authority():
    import aqorath.exercise as exercise

    source_path = Path(exercise.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported_modules = set()
    referenced_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Name):
            referenced_names.add(node.id)

    assert "sqlite3" not in imported_modules
    assert "aqorath.models" not in imported_modules
    assert "aqorath.storage" not in imported_modules
    assert "JournalEntry" not in referenced_names
    assert "JournalLine" not in referenced_names
    assert "get_session" not in referenced_names
