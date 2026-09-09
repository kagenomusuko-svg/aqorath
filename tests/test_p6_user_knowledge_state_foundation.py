"""Phase 6R.1 — frozen contracts for local monouser pedagogical preferences.

Constitution anchors:
- R8 permits one local owner profile and pedagogical/UI preferences, not multiuser/RBAC.
- R12 requires explanation behavior to respect the user's explicit preference.
- R13 permits local tracking of concepts already presented so explanations can progress.

This phase freezes only the state/persistence/application foundation. It does not change
accounting, choose accounts, generate explanations, infer user expertise, or create a
second configuration authority for the historical ``accounting_model`` key.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timezone
import importlib
import inspect
import json
import sqlite3

import pytest
from sqlalchemy import CheckConstraint, Text, create_engine
from sqlmodel import SQLModel, Session, select


DOMAIN_FIELDS = (
    "id",
    "explanation_level",
    "concepts_seen",
    "ui_language",
    "decimal_separator",
    "currency_symbol",
    "preferred_report_format",
    "always_show_professional_view",
    "learned_topics",
)
LEARNED_TOPIC_FIELDS = ("topic", "learned_at")
MODEL_COLUMNS = {
    "id",
    "explanation_level",
    "concepts_seen_json",
    "ui_language",
    "decimal_separator",
    "currency_symbol",
    "preferred_report_format",
    "always_show_professional_view",
    "learned_topics_json",
    "created_at",
}


def _domain():
    return importlib.import_module("aqorath.user_knowledge_state")


def _repository():
    return importlib.import_module("aqorath.user_knowledge_state_repository")


def _state(*, identifier=None, explanation_level="brief"):
    domain = _domain()
    return domain.UserKnowledgeState(
        id=identifier,
        explanation_level=explanation_level,
        concepts_seen=("economic_fact", "double_entry"),
        ui_language="es-MX",
        decimal_separator=".",
        currency_symbol="MX$",
        preferred_report_format="xlsx",
        always_show_professional_view=False,
        learned_topics=(
            domain.LearnedTopic(
                topic="economic_fact",
                learned_at=datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc),
            ),
        ),
    )


def _memory_session():
    # Importing the model first must register the frozen 6R table in canonical metadata.
    import aqorath.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_user_knowledge_domain_is_pure_frozen_and_exactly_local_preference_truth():
    domain = _domain()

    assert tuple(field.name for field in fields(domain.LearnedTopic)) == LEARNED_TOPIC_FIELDS
    assert tuple(field.name for field in fields(domain.UserKnowledgeState)) == DOMAIN_FIELDS

    state = _state()
    with pytest.raises(FrozenInstanceError):
        state.explanation_level = "detailed"
    with pytest.raises(FrozenInstanceError):
        state.learned_topics[0].topic = "changed"

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "get_session",
        "appconfig",
        "accounting_model",
    ):
        assert forbidden not in source


def test_user_knowledge_state_validates_identity_levels_collections_and_boolean_fail_closed():
    domain = _domain()
    base = _state()

    for invalid_id in (0, -1, 2, True, "1"):
        with pytest.raises((TypeError, ValueError)):
            replace(base, id=invalid_id)

    assert replace(base, id=1).id == 1
    for level in ("none", "brief", "detailed"):
        assert replace(base, explanation_level=level).explanation_level == level
    for invalid_level in ("", " verbose", "VERBOSE", "auto", None):
        with pytest.raises((TypeError, ValueError)):
            replace(base, explanation_level=invalid_level)

    for invalid_seen in (
        ["economic_fact"],
        ("economic_fact", "economic_fact"),
        ("",),
        (" spaced ",),
        (1,),
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(base, concepts_seen=invalid_seen)

    for invalid_topics in (
        [base.learned_topics[0]],
        (base.learned_topics[0], base.learned_topics[0]),
        ("economic_fact",),
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(base, learned_topics=invalid_topics)

    for invalid_bool in (0, 1, "false", None):
        with pytest.raises((TypeError, ValueError)):
            replace(base, always_show_professional_view=invalid_bool)


def test_user_preferences_are_explicit_extensible_and_never_normalized_or_inferred():
    domain = _domain()
    base = _state()

    # UI language and report format are explicit preferences, not closed product modes.
    extended = replace(
        base,
        ui_language="pt-BR",
        preferred_report_format="structured-json",
        currency_symbol="R$",
        concepts_seen=("double_entry",),
        learned_topics=(
            domain.LearnedTopic(
                topic="journal_entry",
                learned_at=datetime(2026, 8, 2, 12, 0),
            ),
        ),
    )
    assert extended.ui_language == "pt-BR"
    assert extended.preferred_report_format == "structured-json"
    assert extended.currency_symbol == "R$"
    # Seen concepts and learned topics remain distinct explicit truths; one does not
    # silently add/remove the other.
    assert extended.concepts_seen == ("double_entry",)
    assert extended.learned_topics[0].topic == "journal_entry"

    for invalid_text_field in ("ui_language", "currency_symbol", "preferred_report_format"):
        for invalid in ("", " spaced ", None, 1):
            with pytest.raises((TypeError, ValueError)):
                replace(base, **{invalid_text_field: invalid})

    for separator in (".", ","):
        assert replace(base, decimal_separator=separator).decimal_separator == separator
    for invalid in ("", ";", "..", None):
        with pytest.raises((TypeError, ValueError)):
            replace(base, decimal_separator=invalid)


def test_learned_topic_is_exact_timestamped_value_truth_without_ambient_time_or_normalization():
    domain = _domain()
    timestamp = datetime(2026, 8, 3, 15, 45, 12, 123456, tzinfo=timezone.utc)
    topic = domain.LearnedTopic(topic="fiscal_effect", learned_at=timestamp)
    assert topic.topic == "fiscal_effect"
    assert topic.learned_at is timestamp

    for invalid_topic in ("", " fiscal_effect ", None, 1):
        with pytest.raises((TypeError, ValueError)):
            domain.LearnedTopic(topic=invalid_topic, learned_at=timestamp)
    for invalid_time in (None, "2026-08-03T15:45:12Z", timestamp.date()):
        with pytest.raises((TypeError, ValueError)):
            domain.LearnedTopic(topic="fiscal_effect", learned_at=invalid_time)


def test_user_knowledge_state_is_monouser_and_contains_no_accounting_entity_or_security_authority():
    state = _state()
    forbidden = {
        "user_id",
        "entity_id",
        "role",
        "permissions",
        "password",
        "accounting_model",
        "account_id",
        "debit",
        "credit",
        "amount",
        "journal_entry_id",
        "fiscal_rule_set_id",
    }
    assert forbidden.isdisjoint(DOMAIN_FIELDS)
    for name in forbidden:
        assert not hasattr(state, name)


def test_repository_public_contract_is_minimal_exact_and_non_destructive():
    repository = _repository()
    assert str(inspect.signature(repository.create_user_knowledge_state)) == "(session, state)"
    assert str(inspect.signature(repository.get_user_knowledge_state)) == "(session)"
    assert str(inspect.signature(repository.update_user_knowledge_state)) == "(session, state)"

    for forbidden in (
        "delete_user_knowledge_state",
        "create_user",
        "list_users",
        "set_role",
        "set_accounting_model",
    ):
        assert not hasattr(repository, forbidden)


def test_frozen_v4_additively_creates_exact_singleton_user_knowledge_schema():
    from aqorath import migrations
    from aqorath.models import UserKnowledgeStateRecord

    assert migrations.CURRENT_SCHEMA_VERSION == 5
    assert UserKnowledgeStateRecord.__tablename__ == "userknowledgestate"
    assert set(UserKnowledgeStateRecord.__table__.columns.keys()) == MODEL_COLUMNS

    table = UserKnowledgeStateRecord.__table__
    assert table.c.id.primary_key is True
    required = MODEL_COLUMNS - {"id"}
    assert all(table.c[name].nullable is False for name in required)
    assert isinstance(table.c.concepts_seen_json.type, Text)
    assert isinstance(table.c.learned_topics_json.type, Text)

    assert "user_id" not in table.c
    assert "entity_id" not in table.c
    assert "accounting_model" not in table.c

    checks = [
        str(constraint.sqltext).replace(" ", "")
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert "id=1" in checks

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            UserKnowledgeStateRecord(
                id=2,
                explanation_level="brief",
                concepts_seen_json="[]",
                ui_language="es-MX",
                decimal_separator=".",
                currency_symbol="MX$",
                preferred_report_format="xlsx",
                always_show_professional_view=False,
                learned_topics_json="[]",
            )
        )
        with pytest.raises(Exception):
            session.commit()
        session.rollback()
    engine.dispose()


def test_current_v4_additive_ensure_adds_user_state_without_rewriting_existing_truth(tmp_path):
    from aqorath import migrations

    db_path = tmp_path / "aqorath.db"
    migrations.migrate_database(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE userknowledgestate")
        conn.execute("INSERT INTO appconfig (key, value, created_at) VALUES (?, ?, ?)", (
            "sentinel_preference_test",
            "preserve-me",
            datetime(2026, 8, 4, 10, 0).isoformat(),
        ))
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    finally:
        conn.close()

    migrations._ensure_additive_current_schema(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "userknowledgestate" in tables
        assert conn.execute(
            "SELECT value FROM appconfig WHERE key='sentinel_preference_test'"
        ).fetchone() == ("preserve-me",)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    finally:
        conn.close()


def test_create_and_get_round_trip_preserves_all_explicit_preference_and_learning_truth():
    repository = _repository()
    engine, session = _memory_session()
    try:
        assert repository.get_user_knowledge_state(session) is None
        source = _state()
        created = repository.create_user_knowledge_state(session, source)
        assert created.id == 1
        assert source.id is None
        assert created == replace(source, id=1)

        loaded = repository.get_user_knowledge_state(session)
        assert loaded == created
        assert loaded.concepts_seen == ("economic_fact", "double_entry")
        assert loaded.learned_topics[0].learned_at == datetime(
            2026, 8, 1, 9, 30, tzinfo=timezone.utc
        )
    finally:
        session.close()
        engine.dispose()


def test_singleton_creation_fails_closed_without_replacing_existing_state():
    repository = _repository()
    from aqorath.models import UserKnowledgeStateRecord

    engine, session = _memory_session()
    try:
        first = repository.create_user_knowledge_state(session, _state())
        with pytest.raises((ValueError, RuntimeError)):
            repository.create_user_knowledge_state(
                session,
                replace(_state(), explanation_level="detailed"),
            )

        rows = session.exec(select(UserKnowledgeStateRecord)).all()
        assert len(rows) == 1
        assert repository.get_user_knowledge_state(session) == first
    finally:
        session.close()
        engine.dispose()


def test_update_changes_only_explicit_user_state_and_preserves_singleton_identity():
    repository = _repository()
    from aqorath.models import UserKnowledgeStateRecord

    engine, session = _memory_session()
    try:
        created = repository.create_user_knowledge_state(session, _state())
        updated_request = replace(
            created,
            explanation_level="detailed",
            concepts_seen=("economic_fact", "double_entry", "fiscal_effect"),
            preferred_report_format="pdf",
            always_show_professional_view=True,
        )
        updated = repository.update_user_knowledge_state(session, updated_request)
        assert updated == updated_request
        assert updated.id == 1
        assert repository.get_user_knowledge_state(session) == updated_request
        assert len(session.exec(select(UserKnowledgeStateRecord)).all()) == 1
    finally:
        session.close()
        engine.dispose()


def test_update_requires_existing_persisted_identity_and_rolls_back_commit_failure(monkeypatch):
    repository = _repository()

    engine, session = _memory_session()
    try:
        with pytest.raises((LookupError, ValueError)):
            repository.update_user_knowledge_state(session, replace(_state(), id=1))
        with pytest.raises((TypeError, ValueError)):
            repository.update_user_knowledge_state(session, _state())

        created = repository.create_user_knowledge_state(session, _state())
        before = repository.get_user_knowledge_state(session)
        original_commit = session.commit

        def fail_commit():
            raise RuntimeError("forced commit failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="forced commit failure"):
            repository.update_user_knowledge_state(
                session,
                replace(created, explanation_level="detailed"),
            )
        monkeypatch.setattr(session, "commit", original_commit)
        session.expire_all()
        assert repository.get_user_knowledge_state(session) == before
    finally:
        session.close()
        engine.dispose()


def test_create_rolls_back_when_single_commit_fails(monkeypatch):
    repository = _repository()
    from aqorath.models import UserKnowledgeStateRecord

    engine, session = _memory_session()
    try:
        original_commit = session.commit

        def fail_commit():
            raise RuntimeError("forced commit failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="forced commit failure"):
            repository.create_user_knowledge_state(session, _state())
        monkeypatch.setattr(session, "commit", original_commit)
        assert session.exec(select(UserKnowledgeStateRecord)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_read_fails_closed_on_corrupt_persisted_json_or_semantic_values():
    repository = _repository()
    from aqorath.models import UserKnowledgeStateRecord

    engine, session = _memory_session()
    try:
        record = UserKnowledgeStateRecord(
            id=1,
            explanation_level="brief",
            concepts_seen_json=json.dumps(["economic_fact"]),
            ui_language="es-MX",
            decimal_separator=".",
            currency_symbol="MX$",
            preferred_report_format="xlsx",
            always_show_professional_view=False,
            learned_topics_json=json.dumps([
                {"topic": "economic_fact", "learned_at": "not-a-datetime"}
            ]),
        )
        session.add(record)
        session.commit()
        with pytest.raises((ValueError, TypeError)):
            repository.get_user_knowledge_state(session)

        record.learned_topics_json = "[]"
        record.concepts_seen_json = "not-json"
        session.add(record)
        session.commit()
        with pytest.raises((ValueError, TypeError, json.JSONDecodeError)):
            repository.get_user_knowledge_state(session)
    finally:
        session.close()
        engine.dispose()


def test_repository_uses_only_supplied_session_and_never_becomes_config_or_accounting_engine():
    repository = _repository()
    source = inspect.getsource(repository)
    lowered = source.lower()

    for forbidden in (
        "get_session",
        "appconfig",
        "accounting_model",
        "journalentry",
        "journalline",
        "accountrolebinding",
        "post_entry",
        "resolve_",
        "requests",
        "pathlib",
    ):
        assert forbidden not in lowered


def test_user_state_writes_do_not_mutate_entity_accounting_or_historical_appconfig_truth():
    repository = _repository()
    from aqorath.models import AppConfig, EntityRecord, JournalEntry, UserKnowledgeStateRecord

    engine, session = _memory_session()
    try:
        entity = EntityRecord(
            name="Meriadock A.C.",
            rfc=None,
            legal_personality="persona_moral",
            legal_form="A.C.",
            is_active=True,
        )
        config = AppConfig(key="accounting_model", value="sin_fines")
        entry = JournalEntry(date=datetime(2026, 8, 5, 10, 0), concept="sentinel")
        session.add(entity)
        session.add(config)
        session.add(entry)
        session.commit()
        entity_id, entry_id = entity.id, entry.id

        created = repository.create_user_knowledge_state(session, _state())
        repository.update_user_knowledge_state(
            session,
            replace(created, explanation_level="detailed"),
        )

        assert session.get(EntityRecord, entity_id).name == "Meriadock A.C."
        assert session.get(JournalEntry, entry_id).concept == "sentinel"
        assert session.exec(select(AppConfig).where(AppConfig.key == "accounting_model")).one().value == "sin_fines"
        assert len(session.exec(select(UserKnowledgeStateRecord)).all()) == 1
    finally:
        session.close()
        engine.dispose()


def test_application_exposes_user_knowledge_state_as_exact_thin_delegations(monkeypatch):
    application = importlib.import_module("aqorath.application")
    repository = _repository()

    assert str(inspect.signature(application.create_user_knowledge_state)) == "(session, state)"
    assert str(inspect.signature(application.get_user_knowledge_state)) == "(session)"
    assert str(inspect.signature(application.update_user_knowledge_state)) == "(session, state)"

    calls = []
    marker = object()

    monkeypatch.setattr(
        repository,
        "create_user_knowledge_state",
        lambda session, state: calls.append(("create", session, state)) or marker,
    )
    monkeypatch.setattr(
        repository,
        "get_user_knowledge_state",
        lambda session: calls.append(("get", session)) or marker,
    )
    monkeypatch.setattr(
        repository,
        "update_user_knowledge_state",
        lambda session, state: calls.append(("update", session, state)) or marker,
    )

    session = object()
    state = _state()
    assert application.create_user_knowledge_state(session, state) is marker
    assert application.get_user_knowledge_state(session) is marker
    assert application.update_user_knowledge_state(session, state) is marker
    assert calls == [
        ("create", session, state),
        ("get", session),
        ("update", session, state),
    ]

    source = inspect.getsource(application.create_user_knowledge_state)
    source += inspect.getsource(application.get_user_knowledge_state)
    source += inspect.getsource(application.update_user_knowledge_state)
    assert "_user_knowledge_state_repository" in source
    for forbidden in ("AppConfig", "get_session", "JournalEntry", "Account"):
        assert forbidden not in source
