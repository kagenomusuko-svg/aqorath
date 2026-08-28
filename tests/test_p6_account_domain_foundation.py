"""Phase 6AM.1 — frozen pure Account domain contracts.

R10 requires a governed canonical accounting structure with legitimate extensions, while
the architecture separates pure Domain models from SQLModel persistence. The current
models.Account remains a persistence concern and is intentionally not replaced here.
This phase freezes only the future pure immutable Account domain value; migration,
repositories, catalog integration, hierarchy, uniqueness, posting, and Application remain
outside this authority.
"""

from dataclasses import FrozenInstanceError, fields
import inspect

import pytest


ACCOUNT_FIELDS = (
    "id",
    "code",
    "name",
    "account_type",
    "subtype",
    "nature",
    "is_canonical",
    "name_osc",
    "name_comercial",
)


def _account(**patch):
    from aqorath.account import Account

    values = dict(
        id=None,
        code="1101",
        name="Bancos",
        account_type="asset",
        subtype="current",
        nature="debit",
        is_canonical=True,
        name_osc=None,
        name_comercial=None,
    )
    values.update(patch)
    return Account(**values)


def test_account_domain_is_pure_frozen_and_has_exact_architecture_fields():
    import aqorath.account as domain
    from aqorath.account import Account

    account = _account()
    assert tuple(field.name for field in fields(Account)) == ACCOUNT_FIELDS

    with pytest.raises(FrozenInstanceError):
        account.name = "Cambiado"

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "requests",
        "fastapi",
        "openai",
        "llm",
    ):
        assert forbidden not in source


def test_account_id_is_none_before_identity_or_exact_positive_int():
    assert _account(id=None).id is None
    assert _account(id=7).id == 7

    for invalid in (0, -1, True, False, 1.0, "1"):
        with pytest.raises((TypeError, ValueError)):
            _account(id=invalid)


def test_account_code_and_name_are_exact_nonblank_text_without_normalization():
    for field_name in ("code", "name"):
        for invalid in (None, 7, "", " value", "value ", "   "):
            with pytest.raises((TypeError, ValueError)):
                _account(**{field_name: invalid})

    account = _account(code="01-Activo", name="Caja MXN")
    assert account.code == "01-Activo"
    assert account.name == "Caja MXN"


def test_account_type_is_exact_governed_canonical_structure_token():
    for token in ("asset", "liability", "equity", "income", "expense"):
        assert _account(account_type=token).account_type == token

    for invalid in (
        None,
        7,
        "",
        " asset",
        "asset ",
        "Asset",
        "revenue",
        "activo",
        "other",
    ):
        with pytest.raises((TypeError, ValueError)):
            _account(account_type=invalid)


def test_account_subtype_is_exact_nonblank_open_extensible_text():
    for invalid in (None, 7, "", " current", "current ", "   "):
        with pytest.raises((TypeError, ValueError)):
            _account(subtype=invalid)

    future = _account(subtype="future-specialized-subtype")
    assert future.subtype == "future-specialized-subtype"


def test_account_nature_is_exact_debit_or_credit_without_aliases():
    assert _account(nature="debit").nature == "debit"
    assert _account(nature="credit").nature == "credit"

    for invalid in (
        None,
        7,
        "",
        " debit",
        "debit ",
        "Debit",
        "debtor",
        "creditor",
        "deudora",
        "acreedora",
    ):
        with pytest.raises((TypeError, ValueError)):
            _account(nature=invalid)


def test_is_canonical_is_exact_boolean_and_defaults_true():
    from aqorath.account import Account

    account = Account(
        id=None,
        code="1101",
        name="Bancos",
        account_type="asset",
        subtype="current",
        nature="debit",
    )
    assert account.is_canonical is True
    assert _account(is_canonical=False).is_canonical is False

    for invalid in (0, 1, "true", "false", None):
        with pytest.raises(TypeError):
            _account(is_canonical=invalid)


def test_optional_presentation_names_are_none_or_exact_nonblank_text():
    assert _account(name_osc=None, name_comercial=None).name_osc is None

    account = _account(
        name_osc="Efectivo y equivalentes",
        name_comercial="Bancos",
    )
    assert account.name_osc == "Efectivo y equivalentes"
    assert account.name_comercial == "Bancos"

    for field_name in ("name_osc", "name_comercial"):
        for invalid in (7, "", " valor", "valor ", "   "):
            with pytest.raises((TypeError, ValueError)):
                _account(**{field_name: invalid})


def test_account_preserves_exact_case_spelling_and_user_facing_names():
    account = _account(
        code="A-001",
        name="Banco USD",
        subtype="CashAndEquivalents-v2",
        name_osc="Disponibilidades USD",
        name_comercial="Banco USD",
    )

    assert account.code == "A-001"
    assert account.name == "Banco USD"
    assert account.subtype == "CashAndEquivalents-v2"
    assert account.name_osc == "Disponibilidades USD"
    assert account.name_comercial == "Banco USD"


def test_noncanonical_account_is_legitimate_domain_truth_without_parent_or_origin_fields():
    from aqorath.account import Account

    extension = _account(
        code="1101-LOCAL",
        name="Banco operativo local",
        is_canonical=False,
    )
    assert extension.is_canonical is False

    field_names = {field.name for field in fields(Account)}
    assert "origin" not in field_names
    assert "parent_id" not in field_names


def test_account_domain_excludes_persistence_only_and_unrelated_fields():
    from aqorath.account import Account

    field_names = {field.name for field in fields(Account)}
    persistence_only = {
        "vat_flag",
        "origin",
        "parent_id",
        "created_at",
        "entity_id",
        "account_id",
    }
    assert field_names.isdisjoint(persistence_only)


def test_account_domain_does_not_resolve_uniqueness_hierarchy_or_catalog_membership():
    one = _account(id=None, code="1101")
    two = _account(id=None, code="1101")

    assert one == two
    assert one.code == two.code == "1101"

    import aqorath.account as domain
    source = inspect.getsource(domain).lower()
    for forbidden in (
        "unique",
        "parent_id",
        "catalog",
        "repository",
        "get_session",
        "select(",
    ):
        assert forbidden not in source


def test_account_domain_does_not_infer_type_or_nature_from_code_or_name():
    account = _account(
        code="9999",
        name="Texto que no gobierna clasificación",
        account_type="expense",
        subtype="future-expense",
        nature="credit",
    )

    assert account.account_type == "expense"
    assert account.nature == "credit"


def test_account_domain_is_deterministic_hashable_value_truth():
    first = _account(id=4)
    second = _account(id=4)

    assert first == second
    assert hash(first) == hash(second)

    import aqorath.account as domain
    source = inspect.getsource(domain).lower()
    for forbidden in (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "random",
        "uuid",
        "os.environ",
    ):
        assert forbidden not in source


def test_account_domain_has_no_persistence_posting_or_mutation_api():
    import aqorath.account as domain

    for forbidden_name in (
        "create_account",
        "save_account",
        "delete_account",
        "post_account",
        "set_parent",
        "add_child",
        "bind_role",
        "resolve_account",
    ):
        assert not hasattr(domain, forbidden_name)


def test_account_foundation_does_not_enter_models_application_or_runtime():
    import aqorath.account as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "models",
        "application",
        "account_bindings",
        "account_resolution",
        "posting",
        "reporting_runtime",
        "storage",
        "session",
        "sqlmodel",
        "sqlalchemy",
    ):
        assert forbidden not in source
