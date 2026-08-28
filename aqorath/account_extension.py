"""Pure structural validation for an account extension and its parent."""

from .account import Account


def validate_account_extension_against_parent(extension, parent):
    """Return the same extension when its accounting structure matches its parent."""
    if not isinstance(extension, Account):
        raise TypeError("extension must be Account")
    if not isinstance(parent, Account):
        raise TypeError("parent must be Account")

    if not parent.is_canonical:
        raise ValueError("parent must be canonical")
    if extension.is_canonical:
        raise ValueError("extension must be noncanonical")

    if extension.account_type != parent.account_type:
        raise ValueError("extension account_type must match parent")
    if extension.subtype != parent.subtype:
        raise ValueError("extension subtype must match parent")
    if extension.nature != parent.nature:
        raise ValueError("extension nature must match parent")

    return extension
