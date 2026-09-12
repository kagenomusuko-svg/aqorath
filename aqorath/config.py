"""Retired ``accounting_model`` compatibility tombstone.

The historical ``comercial``/``sin_fines`` selector is not an Aqorath V1
identity authority. Entity + EntityProfile + FiscalProfile + explicit
capabilities are canonical under R15. Historical AppConfig rows may remain in
old SQLite files as inert history; this module no longer reads, writes, or
interprets them.

The importable names remain temporarily so purity/independence tests can
monkeypatch the former dependency and prove modern authorities do not call it.
The private fallback names are inert patch points only; they perform no I/O.
"""

_RETIRED = (
    "accounting_model is retired; use Entity/EntityProfile/FiscalProfile "
    "and explicit capabilities"
)


def _read_fallback_file(*args, **kwargs):
    raise RuntimeError(_RETIRED)


def _write_fallback_file(*args, **kwargs):
    raise RuntimeError(_RETIRED)


def get_accounting_model():
    raise RuntimeError(_RETIRED)


def set_accounting_model(value):
    raise RuntimeError(_RETIRED)


def is_accounting_model_set():
    raise RuntimeError(_RETIRED)


__all__ = [
    "get_accounting_model",
    "set_accounting_model",
    "is_accounting_model_set",
]
