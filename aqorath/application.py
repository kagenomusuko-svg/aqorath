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
  - prepare_fiscal_monetary_confirmation(rounded_amount)
  - confirm_fiscal_monetary_amount(snapshot)
  - declare_fiscal_accounting_treatment(confirmed_monetary_amount, account_role, side)
  - build_fiscal_accounting_effect(declaration)
  - resolve_economic_fact_with_provenance(fact)
  - declare_fiscal_economic_composition(accounting_resolution, fiscal_effect, amount_basis, adjustment_role)
  - compose_fiscal_economic_accounting(declaration)
  - resolve_fiscalized_proposal_accounts(session, fiscalized_proposal, account_bindings)
  - prepare_fiscalized_confirmation(resolved_proposal)
  - confirm_fiscalized_snapshot(snapshot)
  - create_fiscalized_posting_instruction(confirmed_proposal, zero_fiscal_line_policy)
  - execute_fiscalized_posting_instruction(instruction)
  - execute_fiscalized_posting_with_audit(instruction)
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
from . import fiscal_monetary_confirmation as _fiscal_monetary_confirmation
from . import fiscal_accounting_treatment as _fiscal_accounting_treatment
from . import fiscal_accounting_effect as _fiscal_accounting_effect
from . import economic_fact_accounting_provenance as _economic_fact_accounting_provenance
from . import fiscal_economic_composition as _fiscal_economic_composition
from . import fiscalized_accounting_proposal as _fiscalized_accounting_proposal
from . import fiscalized_account_resolution as _fiscalized_account_resolution
from . import fiscalized_confirmation as _fiscalized_confirmation
from . import fiscalized_posting as _fiscalized_posting
from . import fiscalized_posting_execution as _fiscalized_posting_execution
from . import fiscalized_posting_persistence as _fiscalized_posting_persistence


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


def prepare_fiscal_monetary_confirmation(rounded_amount):
    """Prepare the exact rounded fiscal amount for explicit monetary confirmation."""
    return _fiscal_monetary_confirmation.create_fiscal_monetary_confirmation_snapshot(
        rounded_amount,
    )


def confirm_fiscal_monetary_amount(snapshot):
    """Confirm exactly one previously prepared fiscal monetary snapshot."""
    return _fiscal_monetary_confirmation.confirm_fiscal_monetary_snapshot(snapshot)


def declare_fiscal_accounting_treatment(confirmed_monetary_amount, account_role, side):
    """Declare one explicit semantic fiscal accounting role and side."""
    return _fiscal_accounting_treatment.declare_fiscal_accounting_treatment(
        confirmed_monetary_amount,
        account_role,
        side,
    )


def build_fiscal_accounting_effect(declaration):
    """Build one non-postable semantic fiscal accounting effect."""
    return _fiscal_accounting_effect.build_fiscal_accounting_effect(declaration)


def resolve_economic_fact_with_provenance(fact):
    """Resolve one economic fact once while preserving exact accounting provenance."""
    return _economic_fact_accounting_provenance.resolve_economic_fact_with_provenance(
        fact
    )


def declare_fiscal_economic_composition(
    accounting_resolution,
    fiscal_effect,
    amount_basis,
    adjustment_role,
):
    """Declare explicit compatible economic/fiscal composition inputs."""
    return _fiscal_economic_composition.declare_fiscal_economic_composition(
        accounting_resolution,
        fiscal_effect,
        amount_basis,
        adjustment_role,
    )


def compose_fiscal_economic_accounting(declaration):
    """Materialize one explicit fiscal/economic declaration as a balanced proposal."""
    return _fiscalized_accounting_proposal.compose_fiscal_economic_accounting(
        declaration
    )


def resolve_fiscalized_proposal_accounts(
    session,
    fiscalized_proposal,
    account_bindings,
):
    """Resolve one fiscalized semantic proposal through explicit account bindings."""
    return _fiscalized_account_resolution.resolve_fiscalized_proposal_accounts(
        session,
        fiscalized_proposal,
        account_bindings,
    )


def prepare_fiscalized_confirmation(resolved_proposal):
    """Freeze one resolved fiscalized proposal for informed confirmation."""
    return _fiscalized_confirmation.create_fiscalized_confirmation_snapshot(
        resolved_proposal
    )


def confirm_fiscalized_snapshot(snapshot):
    """Confirm exactly one previously prepared fiscalized snapshot."""
    return _fiscalized_confirmation.confirm_fiscalized_snapshot(snapshot)


def create_fiscalized_posting_instruction(
    confirmed_proposal,
    zero_fiscal_line_policy,
):
    """Build one immutable posting instruction from confirmed fiscalized truth."""
    return _fiscalized_posting.create_fiscalized_posting_instruction(
        confirmed_proposal,
        zero_fiscal_line_policy,
    )


def execute_fiscalized_posting_instruction(instruction):
    """Execute exactly one fiscalized posting instruction through its authority."""
    return _fiscalized_posting_execution.execute_fiscalized_posting_instruction(
        instruction
    )


def execute_fiscalized_posting_with_audit(instruction):
    """Persist one fiscalized posting instruction and its fiscal audit atomically."""
    return _fiscalized_posting_persistence.execute_fiscalized_posting_with_audit(
        instruction
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
