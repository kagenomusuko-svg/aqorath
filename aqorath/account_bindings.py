"""Persistent account-role binding authority — Phase 2D.3.

Bindings are stored in SQLite as role -> account_id. Account.code remains owned by
Account and is derived at read time; it is never duplicated in binding persistence.
All operations use the caller-supplied ORM session.
"""

from sqlmodel import select

from . import catalog as _catalog
from .models import Account, AccountRoleBinding


__all__ = [
    "set_account_binding",
    "get_account_binding",
    "get_account_bindings",
]


def _validate_role(role):
    if not isinstance(role, str):
        raise TypeError("account role must be a string")
    if not role or role.strip() != role:
        raise ValueError("account role must be non-empty and contain no surrounding whitespace")


def _validate_account_code(account_code):
    if not isinstance(account_code, str):
        raise TypeError("account code must be a string")
    if not account_code or account_code.strip() != account_code:
        raise ValueError("account code must be non-empty and contain no surrounding whitespace")


def set_account_binding(session, role, account_code, *, commit=True):
    """Persist or stage one role binding after validating the concrete Account."""
    _validate_role(role)
    _validate_account_code(account_code)

    account = _catalog.resolve_account_by_code(session, account_code)
    if account is None:
        raise LookupError(
            f"Cannot bind role '{role}': account '{account_code}' does not exist"
        )
    if getattr(account, "id", None) is None:
        raise ValueError(
            f"Cannot bind role '{role}': account '{account_code}' has no persistent id"
        )

    try:
        binding = session.exec(
            select(AccountRoleBinding).where(AccountRoleBinding.role == role)
        ).one_or_none()

        if binding is None:
            binding = AccountRoleBinding(role=role, account_id=account.id)
        else:
            binding.account_id = account.id

        session.add(binding)
        session.flush()
        if commit:
            session.commit()
    except Exception:
        session.rollback()
        raise

    return None


def get_account_binding(session, role):
    """Return the current Account.code for a role, or None when the role is unbound."""
    _validate_role(role)

    binding = session.exec(
        select(AccountRoleBinding).where(AccountRoleBinding.role == role)
    ).one_or_none()
    if binding is None:
        return None

    account = session.get(Account, binding.account_id)
    if account is None:
        raise LookupError(
            f"Binding for role '{role}' references missing account id {binding.account_id}"
        )

    return account.code


def get_account_bindings(session, roles):
    """Return role -> current Account.code for all requested roles, failing if any is missing."""
    if isinstance(roles, str):
        raise TypeError("roles must be an iterable of role strings, not a single string")

    result = {}
    for role in roles:
        code = get_account_binding(session, role)
        if code is None:
            raise KeyError(f"No account binding configured for role '{role}'")
        result[role] = code

    return result
