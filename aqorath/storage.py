from pathlib import Path
import os
from typing import Optional

from sqlmodel import Session, create_engine
from sqlalchemy import event, inspect as sa_inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session as SASession

# DEFAULT DB location (user local data dir)
DEFAULT_DB = Path.home() / ".local" / "share" / "aqorath" / "aqorath.db"

# Module-level state
_DB_PATH: Optional[str] = None
_engine = None
_account_listener_registered = False
_journal_listener_registered = False


def get_db_path() -> str:
    """
    Devuelve la ruta absoluta del DB usado por la aplicación.
    Priorizamos la variable de entorno AQORATH_DB si está establecida.
    """
    env = os.environ.get("AQORATH_DB")
    if env:
        return str(Path(env).resolve())
    return str(DEFAULT_DB)


DB_PATH = get_db_path()


def _register_account_listener():
    """Registra listeners que gobiernan cuentas canónicas y de entidad."""
    global _account_listener_registered
    if _account_listener_registered:
        return

    try:
        from aqorath.models import Account
        from aqorath.catalog import load_catalog_codes
    except Exception as exc:
        raise RuntimeError(
            "No se pudo inicializar la protección canónica del catálogo de cuentas."
        ) from exc

    @event.listens_for(Account, "before_insert")
    def _govern_account_insert(mapper, connection: Connection, target):
        try:
            catalog_codes = load_catalog_codes()
        except Exception as exc:
            raise RuntimeError(
                "No se pudo cargar el catálogo para validar códigos de cuenta."
            ) from exc

        code_str = str(getattr(target, "code", "")).strip()
        origin = str(getattr(target, "origin", "canonical")).strip().lower()
        parent_id = getattr(target, "parent_id", None)
        name = str(getattr(target, "name", "")).strip()
        nature = str(getattr(target, "nature", "")).strip()

        if not code_str:
            raise ValueError("Inserción denegada: código de cuenta vacío.")
        if not name:
            raise ValueError("Inserción denegada: nombre de cuenta vacío.")

        if origin == "canonical":
            if parent_id is not None:
                raise ValueError(
                    f"Cuenta canónica '{code_str}' no puede tener parent_id."
                )
            if code_str not in catalog_codes:
                raise ValueError(
                    f"Inserción denegada: la cuenta canónica '{code_str}' no existe en el catálogo."
                )
        elif origin == "entity":
            if parent_id is None:
                raise ValueError(
                    f"Cuenta de entidad '{code_str}' debe tener parent_id."
                )
            if "." not in code_str:
                raise ValueError(
                    f"Código de entidad '{code_str}' debe tener formato parent_code.NNN"
                )
            parts = code_str.rsplit(".", 1)
            if len(parts) != 2 or not parts[1].isdigit() or len(parts[1]) != 3:
                raise ValueError(
                    f"Código de entidad '{code_str}' debe tener formato parent_code.NNN (3 dígitos)"
                )
            parent_code_expected = parts[0]
            try:
                parent_result = connection.execute(
                    text("SELECT id, code, origin, nature FROM account WHERE id = :pid"),
                    {"pid": parent_id},
                ).fetchone()
                if not parent_result:
                    raise ValueError(f"Parent account con id {parent_id} no existe.")
                _, parent_code_db, parent_origin, parent_nature = parent_result
                if parent_origin != "canonical":
                    raise ValueError(
                        f"Parent debe ser canónico, no entidad. Parent code: {parent_code_db}"
                    )
                if parent_code_db != parent_code_expected:
                    raise ValueError(
                        f"Código entity '{code_str}' refiere parent '{parent_code_expected}' pero parent actual es '{parent_code_db}'"
                    )
                if parent_code_db not in catalog_codes:
                    raise ValueError(
                        f"Parent canónico '{parent_code_db}' no está en catálogo."
                    )
                if nature != parent_nature:
                    raise ValueError(
                        f"Entidad hereda naturaleza '{parent_nature}' del padre, no puede ser '{nature}'"
                    )
            except Exception as exc:
                if any(token in str(exc) for token in ("no existe", "refiere", "hereda")):
                    raise
                raise ValueError(f"Error validando parent: {exc}") from exc
        else:
            raise ValueError(f"origin inválido: {origin}. Debe ser 'canonical' o 'entity'.")

    @event.listens_for(Account, "before_update")
    def _prevent_structural_changes(mapper, connection: Connection, target):
        state = sa_inspect(target)
        if not state.has_identity:
            return
        if state.attrs.code.history.has_changes():
            old_val = state.attrs.code.history.deleted[0] if state.attrs.code.history.deleted else None
            new_val = state.attrs.code.history.added[0] if state.attrs.code.history.added else target.code
            raise ValueError(f"No se puede modificar code de cuenta: {old_val} → {new_val}")
        if state.attrs.origin.history.has_changes():
            old_val = state.attrs.origin.history.deleted[0] if state.attrs.origin.history.deleted else None
            new_val = state.attrs.origin.history.added[0] if state.attrs.origin.history.added else target.origin
            raise ValueError(f"No se puede modificar origin de cuenta: {old_val} → {new_val}")
        if state.attrs.parent_id.history.has_changes():
            old_val = state.attrs.parent_id.history.deleted[0] if state.attrs.parent_id.history.deleted else None
            new_val = state.attrs.parent_id.history.added[0] if state.attrs.parent_id.history.added else target.parent_id
            raise ValueError(f"No se puede modificar parent_id de cuenta: {old_val} → {new_val}")
        if target.origin == "entity" and target.parent_id:
            try:
                parent_nature = connection.execute(
                    text("SELECT nature FROM account WHERE id = :pid"),
                    {"pid": target.parent_id},
                ).scalar()
                if parent_nature and target.nature != parent_nature:
                    raise ValueError(
                        f"Naturaleza de entidad debe heredarse del padre. Padre: {parent_nature}, Intento: {target.nature}"
                    )
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f"Error validating entity nature: {exc}") from exc

    _account_listener_registered = True


def _register_journal_invariant_listener():
    """Install the fail-closed JournalEntry persistence guard required by R4."""
    global _journal_listener_registered
    if _journal_listener_registered:
        return

    marker = "_aqorath_journal_invariant_listener_registered"
    if getattr(SASession, marker, False):
        _journal_listener_registered = True
        return

    try:
        from aqorath.ledger_invariants import (
            LedgerInvariantError,
            validate_journal_line_money,
            validate_journal_lines,
        )
        from aqorath.models import JournalEntry, JournalLine
    except Exception as exc:
        raise RuntimeError(
            "No se pudo inicializar la protección de invariantes del libro mayor."
        ) from exc

    new_entries_key = "_aqorath_new_journal_entries"
    affected_entries_key = "_aqorath_affected_journal_entry_ids"
    deleted_entries_key = "_aqorath_deleted_journal_entry_ids"

    def _enabled(session: SASession) -> bool:
        try:
            bind = session.get_bind()
        except Exception:
            return False
        engine = getattr(bind, "engine", bind)
        return bool(getattr(engine, "_aqorath_ledger_invariants_enabled", False))

    def _track(session: SASession) -> None:
        if not _enabled(session):
            return

        new_entries = session.info.setdefault(new_entries_key, [])
        affected_ids = session.info.setdefault(affected_entries_key, set())
        deleted_ids = session.info.setdefault(deleted_entries_key, set())

        for obj in list(session.new):
            if isinstance(obj, JournalEntry) and obj not in new_entries:
                if obj.state not in ('draft', 'posted'):
                    raise LedgerInvariantError('New JournalEntry state must be draft or posted')
                from aqorath.accounting_period_repository import require_open_period
                obj.period_id = require_open_period(session, obj.date, obj.period_id).id
                new_entries.append(obj)

        for obj in list(session.dirty):
            if isinstance(obj, JournalEntry) and obj.id is not None:
                from aqorath.accounting_period_repository import validate_persisted_period, require_open_period
                state = sa_inspect(obj)
                persisted_id = state.identity[0]
                persisted_state = session.connection().execute(text('SELECT state FROM journalentry WHERE id=:id'), {'id': persisted_id}).scalar()
                changed = any(attr.history.has_changes() for attr in state.attrs)
                if persisted_state == "posted" and state.attrs.date.history.has_changes():
                    validate_persisted_period(session, obj.id)
                if persisted_state in ("posted", "reversed") and changed:
                    raise LedgerInvariantError("Posted JournalEntry is immutable; use reversal")
                if obj.state not in ('draft', 'posted'):
                    raise LedgerInvariantError('Use canonical reversal for reversed state')
                validate_persisted_period(session, obj.id)
                obj.period_id = require_open_period(session, obj.date, obj.period_id).id
                affected_ids.add(int(obj.id))

        for obj in list(session.deleted):
            if isinstance(obj, JournalEntry) and obj.id is not None:
                persisted_state = session.connection().execute(text('SELECT state FROM journalentry WHERE id=:id'), {'id': sa_inspect(obj).identity[0]}).scalar()
                if persisted_state in ("posted", "reversed"):
                    raise LedgerInvariantError("Posted JournalEntry cannot be deleted; use reversal")
                deleted_ids.add(int(obj.id))

        for index, obj in enumerate(list(session.new) + list(session.dirty)):
            if isinstance(obj, JournalLine):
                validate_journal_line_money(obj, index=index)

        touched_lines = list(session.new) + list(session.dirty) + list(session.deleted)
        for obj in touched_lines:
            if not isinstance(obj, JournalLine):
                continue
            state = sa_inspect(obj)
            history = state.attrs.entry_id.history
            for old_entry_id in history.deleted:
                if old_entry_id is not None:
                    affected_ids.add(int(old_entry_id))
            current_entry_id = getattr(obj, "entry_id", None)
            if current_entry_id is not None:
                affected_ids.add(int(current_entry_id))
            owners = set(history.deleted)
            owners.add(current_entry_id)
            if state.identity is not None:
                owners.add(session.connection().execute(text('SELECT entry_id FROM journalline WHERE id=:id'), {'id': state.identity[0]}).scalar())
            staged_ids = {e.id for e in new_entries}
            for owner_id in owners - staged_ids - {None}:
                owner_state = session.connection().execute(text('SELECT state FROM journalentry WHERE id=:id'), {'id': owner_id}).scalar()
                if owner_state in ('posted', 'reversed'):
                    raise LedgerInvariantError('Consolidated JournalLine is immutable; use reversal')

    def _tracked_entry_ids(session: SASession) -> set[int]:
        ids = set(session.info.get(affected_entries_key, set()))
        for entry in session.info.get(new_entries_key, []):
            entry_id = getattr(entry, "id", None)
            if entry_id is not None:
                ids.add(int(entry_id))
        ids.difference_update(session.info.get(deleted_entries_key, set()))
        return ids

    def _load_persisted_lines(session: SASession, entry_id: int):
        rows = session.connection().execute(
            text(
                """
                SELECT
                    jl.id,
                    jl.entry_id,
                    jl.account_id,
                    jl.account_code,
                    jl.debit,
                    jl.credit,
                    a.id AS resolved_account_id,
                    a.code AS resolved_account_code
                FROM journalline jl
                LEFT JOIN account a ON a.id = jl.account_id
                WHERE jl.entry_id = :entry_id
                ORDER BY jl.id
                """
            ),
            {"entry_id": entry_id},
        ).mappings().all()

        materialized = []
        for row in rows:
            item = dict(row)
            if item["resolved_account_id"] is None:
                raise LedgerInvariantError(
                    f"JournalEntry {entry_id}: JournalLine {item['id']} references a missing Account"
                )
            if str(item["account_code"]) != str(item["resolved_account_code"]):
                raise LedgerInvariantError(
                    f"JournalEntry {entry_id}: JournalLine {item['id']} account identity mismatch"
                )
            materialized.append(item)
        return materialized

    def _validate_ids(session: SASession, entry_ids: set[int]) -> None:
        for entry_id in sorted(entry_ids):
            validate_journal_lines(_load_persisted_lines(session, entry_id))
            from aqorath.accounting_period_repository import validate_persisted_period
            validate_persisted_period(session, entry_id)

    def _clear_tracking(session: SASession) -> None:
        session.info.pop("_aqorath_annual_closing", None)
        session.info.pop(new_entries_key, None)
        session.info.pop(affected_entries_key, None)
        session.info.pop(deleted_entries_key, None)

    def _before_flush(session, flush_context, instances):
        _track(session)

    def _before_commit(session):
        if not _enabled(session):
            return
        if session.new or session.dirty or session.deleted:
            session.flush()
        entry_ids = _tracked_entry_ids(session)
        if entry_ids:
            _validate_ids(session, entry_ids)

    def _after_transaction_end(session, transaction):
        if transaction.parent is None:
            _clear_tracking(session)

    event.listen(SASession, "before_flush", _before_flush)
    event.listen(SASession, "before_commit", _before_commit)
    event.listen(SASession, "after_transaction_end", _after_transaction_end)
    setattr(SASession, marker, True)
    _journal_listener_registered = True


def _create_engine(db_path: str):
    from aqorath.migrations import migrate_database

    migrate_database(db_path)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    setattr(engine, "_aqorath_ledger_invariants_enabled", True)
    _register_account_listener()
    _register_journal_invariant_listener()
    return engine


def get_engine():
    global _engine, _DB_PATH, DB_PATH
    desired_path = get_db_path()
    if _engine is None or _DB_PATH != desired_path:
        if _engine is not None:
            try:
                _engine.dispose()
            except Exception:
                pass
        _engine = _create_engine(desired_path)
        _DB_PATH = desired_path
        DB_PATH = desired_path
    return _engine


def get_session() -> Session:
    return Session(get_engine())


def init_db(db_path: Optional[str] = None, create_tables: bool = False):
    global _engine, _DB_PATH, DB_PATH
    if db_path:
        os.environ["AQORATH_DB"] = str(Path(db_path).resolve())
    _DB_PATH = get_db_path()
    DB_PATH = _DB_PATH
    _engine = _create_engine(_DB_PATH)

    if create_tables:
        from sqlmodel import SQLModel
        SQLModel.metadata.create_all(_engine)

    _register_account_listener()
    _register_journal_invariant_listener()
    return _engine
