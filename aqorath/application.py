"""
Aqorath Application Boundary

Canonical interface-agnostic facade. Adapters call this module; accounting,
resolution, confirmation, binding, reporting, fiscal and persistence rules remain in their
specialized authorities.

Public API includes the legacy template/trial-balance facade plus the economic-fact flow:
  - preview_economic_fact(fact)
  - prepare_economic_fact_confirmation(session, fact, account_bindings)
  - prepare_configured_economic_fact_confirmation(session, fact)
  - set_account_binding(session, role, account_code)
  - get_account_binding(session, role)
  - confirm_economic_fact(snapshot)
  - post_confirmed_economic_fact(confirmed_proposal)
  - get_financial_report_snapshot(as_of=None)
  - get_income_statement_view(as_of=None)
  - get_balance_sheet_view(as_of=None)
  - get_financial_statements_bundle(as_of=None)
  - get_financial_report_csv(as_of=None)
  - get_financial_report_xlsx(as_of=None)
  - get_financial_statements_xlsx(as_of=None)
  - get_financial_statements_pdf(as_of=None)
  - calculate_fiscal_rate_for_date(session, rule_key, effective_date, context, base)
  - declare_fiscal_rate_applicability(fact, effective_date, context, rule_key, base)
  - calculate_declared_fiscal_rate(session, declaration)
  - prepare_fiscal_confirmation(declared_calculation)
  - confirm_fiscal_treatment(snapshot)
  - round_confirmed_fiscal_amount(confirmed_treatment, policy)
"""

from . import core as _core
from . import economic_facts as _economic_facts
from . import account_resolution as _account_resolution
from . import account_bindings as _account_bindings
from . import confirmation as _confirmation
from . import posting as _posting
from . import posting_execution as _posting_execution
from . import reporting_runtime as _reporting_runtime
from . import reporting_export as _reporting_export
from . import fiscal_runtime as _fiscal_runtime
from . import fiscal_applicability as _fiscal_applicability
from . import fiscal_declaration_runtime as _fiscal_declaration_runtime
from . import fiscal_confirmation as _fiscal_confirmation
from . import fiscal_rounding as _fiscal_rounding


def list_templates():
    """Enumerate available contable templates."""
    return _core.list_templates()


def preview_template(template_key, amount, ctx=None):
    """Preview a template accounting entry without persistence."""
    return _core.generate_preview(template_key, amount, ctx=ctx)


def post_template(first, amount=None, ctx=None, user=None):
    """Persist a template/full entry through the canonical core authority."""
    return _core.post_entry(first, amount=amount, ctx=ctx, user=user)


def get_trial_balance(as_of=None):
    """Query the consolidated trial balance from the canonical SQLite authority."""
    return _core.trial_balance(as_of=as_of)


def get_financial_report_snapshot(as_of=None):
    """Return the canonical immutable financial reporting snapshot."""
    return _reporting_runtime.get_financial_report_snapshot(as_of=as_of)


def get_income_statement_view(as_of=None):
    """Return the canonical formal Income Statement view."""
    return _reporting_runtime.get_income_statement_view(as_of=as_of)


def get_balance_sheet_view(as_of=None):
    """Return the canonical formal Balance Sheet view."""
    return _reporting_runtime.get_balance_sheet_view(as_of=as_of)


def get_financial_statements_bundle(as_of=None):
    """Return coherent formal financial statements from one canonical snapshot."""
    return _reporting_runtime.get_financial_statements_bundle(as_of=as_of)


def get_financial_report_csv(as_of=None):
    """Return canonical financial-report CSV text."""
    return _reporting_export.get_financial_report_csv(as_of=as_of)


def get_financial_report_xlsx(as_of=None):
    """Return canonical raw financial-report XLSX bytes."""
    return _reporting_export.get_financial_report_xlsx(as_of=as_of)


def get_financial_statements_xlsx(as_of=None):
    """Return canonical formal financial-statements XLSX bytes."""
    return _reporting_export.get_financial_statements_xlsx(as_of=as_of)


def get_financial_statements_pdf(as_of=None):
    """Return canonical formal financial-statements PDF bytes."""
    return _reporting_export.get_financial_statements_pdf(as_of=as_of)


def calculate_fiscal_rate_for_date(session, rule_key, effective_date, context, base):
    """Delegate explicit dated fiscal-rate calculation to the fiscal runtime."""
    return _fiscal_runtime.calculate_fiscal_rate_for_date(
        session,
        rule_key,
        effective_date,
        context,
        base,
    )


def declare_fiscal_rate_applicability(fact, effective_date, context, rule_key, base):
    """Declare one explicit rate-based fiscal treatment without calculating it."""
    return _fiscal_applicability.declare_fiscal_rate_applicability(
        fact,
        effective_date,
        context,
        rule_key,
        base,
    )


def calculate_declared_fiscal_rate(session, declaration):
    """Calculate exactly one previously explicit fiscal-rate declaration."""
    return _fiscal_declaration_runtime.calculate_declared_fiscal_rate(
        session,
        declaration,
    )


def prepare_fiscal_confirmation(declared_calculation):
    """Prepare the exact immutable fiscal truth for informed confirmation."""
    return _fiscal_confirmation.create_fiscal_confirmation_snapshot(
        declared_calculation,
    )


def confirm_fiscal_treatment(snapshot):
    """Confirm exactly one previously prepared fiscal confirmation snapshot."""
    return _fiscal_confirmation.confirm_fiscal_snapshot(snapshot)


def round_confirmed_fiscal_amount(confirmed_treatment, policy):
    """Round one confirmed fiscal amount using one explicit supplied policy."""
    return _fiscal_rounding.round_confirmed_fiscal_amount(
        confirmed_treatment,
        policy,
    )


def preview_economic_fact(fact):
    """Resolve a structured EconomicFact to a semantic AccountingProposal."""
    return _economic_facts.resolve_economic_fact(fact)


def set_account_binding(session, role, account_code):
    """Persist or replace one semantic role binding using the supplied session."""
    return _account_bindings.set_account_binding(session, role, account_code)


def get_account_binding(session, role):
    """Return the configured concrete account code for one semantic role."""
    return _account_bindings.get_account_binding(session, role)


def prepare_economic_fact_confirmation(session, fact, account_bindings):
    """Resolve an economic fact through explicit concrete-account bindings."""
    proposal = _economic_facts.resolve_economic_fact(fact)
    resolved = _account_resolution.resolve_proposal_accounts(
        session,
        proposal,
        account_bindings,
    )
    return _confirmation.create_confirmation_snapshot(resolved)


def prepare_configured_economic_fact_confirmation(session, fact):
    """Resolve an economic fact using persistent SQLite account-role bindings."""
    proposal = _economic_facts.resolve_economic_fact(fact)
    roles = tuple(line.account_role for line in proposal.lines)
    account_bindings = _account_bindings.get_account_bindings(session, roles)
    resolved = _account_resolution.resolve_proposal_accounts(
        session,
        proposal,
        account_bindings,
    )
    return _confirmation.create_confirmation_snapshot(resolved)


def confirm_economic_fact(snapshot):
    """Record the explicit in-memory confirmation of exactly one snapshot."""
    return _confirmation.confirm_snapshot(snapshot)


def post_confirmed_economic_fact(confirmed_proposal):
    """Build and execute posting only from a previously confirmed proposal."""
    instruction = _posting.create_posting_instruction(confirmed_proposal)
    return _posting_execution.execute_posting_instruction(instruction)
