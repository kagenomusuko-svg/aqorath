"""Phase 6AN.1 — frozen pure account-extension structural contracts.

R10 and the catalog policy define entity accounts as legitimate extensions beneath a
canonical account. The canonical parent governs accounting classification; code
allocation, parent persistence, entity ownership, and runtime catalog lookup remain
separate concerns. This phase therefore freezes only a pure structural validator over
two explicit Account domain values. It does not introduce a speculative AccountExtension
dataclass, generate codes, resolve parents, persist anything, or enter Application.
"""

import inspect

import pytest


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


def _parent(**patch):
    values = dict(
        id=10,
        code="1101",
        name="Bancos",
        account_type="asset",
        subtype="current",
        nature="debit",
        is_canonical=True,
    )
    values.update(patch)
    return _account(**values)


def _extension(**patch):
    values = dict(
        id=None,
        code="1101.001",
        name="BBVA",
        account_type="asset",
        subtype="current",
        nature="debit",
        is_canonical=False,
    )
    values.update(patch)
    return _account(**values)


def test_account_extension_public_contract_is_exact_and_pure():
    import aqorath.account_extension as domain

    function = domain.validate_account_extension_against_parent
    assert tuple(inspect.signature(function).parameters) == ("extension", "parent")
    assert not hasattr(domain, "AccountExtension")

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


def test_extension_and_parent_require_nominal_accounts():
    from aqorath.account_extension import validate_account_extension_against_parent

    extension = _extension()
    parent = _parent()

    for invalid_extension in (object(), {}, "1101.001", None):
        with pytest.raises(TypeError):
            validate_account_extension_against_parent(invalid_extension, parent)

    for invalid_parent in (object(), {}, "1101", None):
        with pytest.raises(TypeError):
            validate_account_extension_against_parent(extension, invalid_parent)


def test_parent_must_be_canonical():
    from aqorath.account_extension import validate_account_extension_against_parent

    with pytest.raises(ValueError):
        validate_account_extension_against_parent(
            _extension(),
            _parent(is_canonical=False),
        )


def test_extension_must_be_noncanonical():
    from aqorath.account_extension import validate_account_extension_against_parent

    with pytest.raises(ValueError):
        validate_account_extension_against_parent(
            _extension(is_canonical=True),
            _parent(),
        )


def test_extension_inherits_exact_account_type_from_parent():
    from aqorath.account_extension import validate_account_extension_against_parent

    with pytest.raises(ValueError):
        validate_account_extension_against_parent(
            _extension(account_type="expense", nature="debit"),
            _parent(account_type="asset", nature="debit"),
        )

    matching = _extension(account_type="income", subtype="operating", nature="credit")
    parent = _parent(account_type="income", subtype="operating", nature="credit")
    assert validate_account_extension_against_parent(matching, parent) is matching


def test_extension_inherits_exact_subtype_from_parent():
    from aqorath.account_extension import validate_account_extension_against_parent

    with pytest.raises(ValueError):
        validate_account_extension_against_parent(
            _extension(subtype="noncurrent"),
            _parent(subtype="current"),
        )


def test_extension_inherits_exact_nature_from_parent():
    from aqorath.account_extension import validate_account_extension_against_parent

    with pytest.raises(ValueError):
        validate_account_extension_against_parent(
            _extension(nature="credit"),
            _parent(nature="debit"),
        )


def test_matching_structure_returns_exact_extension_identity():
    from aqorath.account_extension import validate_account_extension_against_parent

    extension = _extension()
    parent = _parent()
    result = validate_account_extension_against_parent(extension, parent)

    assert result is extension


def test_parent_and_extension_ids_are_opaque_and_need_not_be_persisted():
    from aqorath.account_extension import validate_account_extension_against_parent

    transient_parent = _parent(id=None)
    transient_extension = _extension(id=None)
    persisted_extension = _extension(id=999)

    assert (
        validate_account_extension_against_parent(
            transient_extension,
            transient_parent,
        )
        is transient_extension
    )
    assert (
        validate_account_extension_against_parent(
            persisted_extension,
            transient_parent,
        )
        is persisted_extension
    )


def test_extension_code_is_opaque_to_structural_authority():
    from aqorath.account_extension import validate_account_extension_against_parent

    extension = _extension(code="CUSTOM-X")
    parent = _parent(code="1101")

    assert validate_account_extension_against_parent(extension, parent) is extension
    assert extension.code == "CUSTOM-X"


def test_extension_names_and_presentation_labels_may_differ_from_parent():
    from aqorath.account_extension import validate_account_extension_against_parent

    parent = _parent(
        name="Bancos",
        name_osc="Efectivo y equivalentes",
        name_comercial="Bancos",
    )
    extension = _extension(
        name="Cuenta operativa MXN",
        name_osc="Banco del programa",
        name_comercial="Cuenta operativa",
    )

    assert validate_account_extension_against_parent(extension, parent) is extension


def test_parent_and_extension_values_are_not_mutated():
    from aqorath.account_extension import validate_account_extension_against_parent

    parent = _parent()
    extension = _extension()
    before_parent = parent
    before_extension = extension

    validate_account_extension_against_parent(extension, parent)

    assert parent == before_parent
    assert extension == before_extension
    assert parent is before_parent
    assert extension is before_extension


def test_validator_does_not_create_or_transform_account_values():
    import aqorath.account_extension as domain

    extension = _extension(code="LOCAL-BANK", name="Banco local")
    parent = _parent()
    result = domain.validate_account_extension_against_parent(extension, parent)

    assert result is extension
    assert result.code == "LOCAL-BANK"
    assert result.name == "Banco local"

    for forbidden_name in (
        "create_extension",
        "build_extension",
        "generate_extension_code",
        "next_extension_code",
        "copy_account",
    ):
        assert not hasattr(domain, forbidden_name)


def test_validator_does_not_resolve_catalog_parent_or_entity_ownership():
    import aqorath.account_extension as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "parent_id",
        "entity_id",
        "origin",
        "catalog",
        "repository",
        "get_session",
        "select(",
        "load_active_entity",
    ):
        assert forbidden not in source


def test_validator_does_not_enter_persistence_application_or_runtime():
    import aqorath.account_extension as domain
    import aqorath.application as application

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

    application_source = inspect.getsource(application).lower()
    assert "account_extension" not in application_source
    assert "validate_account_extension_against_parent" not in application_source


def test_account_extension_structure_is_deterministic_and_has_no_ambient_inputs():
    import aqorath.account_extension as domain

    first_extension = _extension()
    second_extension = _extension()
    parent = _parent()

    first = domain.validate_account_extension_against_parent(first_extension, parent)
    second = domain.validate_account_extension_against_parent(second_extension, parent)
    assert first == second

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
