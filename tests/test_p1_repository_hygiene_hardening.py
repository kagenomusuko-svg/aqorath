"""
P1E.2B Repository Hygiene Hardening Regressions

Tests to prevent re-introduction of residual artifacts:
- Manual database backups
- Editor lockfiles
- Paths with leading/trailing whitespace
"""
import subprocess
from pathlib import Path


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


def test_git_does_not_track_database_backup_variants():
    """
    P1E.2B/1E.2C: Git must not track manual database backup variants.

    Case-insensitive detection of:
    - Database filenames (.db, .sqlite, .sqlite3) + backup indicators (bak, manualbak)
    
    Examples (all forbidden):
    - test.db.bak.2026
    - backup.SQLITE.ManualBak.2026
    - mydb.DB.BAK
    """
    tracked = _git_tracked_files()

    violations = []
    for path in tracked:
        filename = Path(path).name.lower()

        # Detect: any database name + any backup indicator
        is_database_file = ".db" in filename or ".sqlite" in filename
        is_backup_file = "bak" in filename

        if is_database_file and is_backup_file:
            violations.append(path)

    assert not violations, (
        f"Git tracks database backup variants:\n{chr(10).join(violations)}"
    )


def test_git_does_not_track_editor_lockfiles_or_whitespace_paths():
    """
    P1E.2B/1E.2C: Git must not track editor lockfiles or paths with
    leading/trailing whitespace in path components.

    Forbidden in any path component:
    - Starting with .~lock. (LibreOffice locks)
    - Starting with ~$ (Excel locks)
    - Having leading/trailing whitespace
    
    Examples (all forbidden):
    - ~$file.xlsx
    - assets/~$backup.xls
    - .~lock.catalogo.xlsx#
    - nested/path/.~lock.file#
    - assets/catalogo.csv<SPACE>
    """
    tracked = _git_tracked_files()

    violations = []
    for path in tracked:
        path_obj = Path(path)
        violates = False

        for component in path_obj.parts:
            # Check for editor lockfile patterns
            if component.startswith(".~lock.") or component.startswith("~$"):
                violations.append(path)
                violates = True
                break

            # Check for leading/trailing whitespace
            if component != component.strip():
                violations.append(path)
                violates = True
                break

        if violates:
            continue

    assert not violations, (
        f"Git tracks editor lockfiles or whitespace-invalid paths:\n{chr(10).join(violations)}"
    )
