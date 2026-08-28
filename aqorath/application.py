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
  - load_fiscal_posting_audit_snapshot(session, entry_id)
  - create_entity(session, entity)
  - get_active_entity(session)
  - register_fiscal_profile(session, profile)
  - get_fiscal_profile_for_date(session, entity_id, effective_date)
  - create_third_party(session, third_party)
  - get_third_party(session, entity_id, third_party_id)
  - list_third_parties(session, entity_id, include_inactive=False)
  - set_third_party_active(session, entity_id, third_party_id, is_active)
  - create_document_reference(session, document_reference)
  - get_document_reference(session, document_reference_id)
  - list_document_references(session, entry_id)
  - register_cfdi_import_metadata(session, metadata)
  - get_cfdi_import_metadata(session, document_reference_id)
  - create_analytical_dimension(session, dimension)
  - get_analytical_dimension(session, entity_id, dimension_id)
  - list_analytical_dimensions(session, entity_id)
  - create_analytical_dimension_value(session, dimension_value)
  - list_analytical_dimension_values(session, dimension_id)
  - assign_analytical_dimension_value(session, journal_line_id, dimension_value_id)
  - list_journal_line_analytics(session, journal_line_id)
  - create_fixed_asset(session, fixed_asset)
  - get_fixed_asset(session, entity_id, fixed_asset_id)
  - list_fixed_assets(session, entity_id, include_inactive=False)
  - set_fixed_asset_active(session, entity_id, fixed_asset_id, is_active)
  - calculate_fixed_asset_monthly_depreciation(fixed_asset)
  - allocate_fixed_asset_monthly_depreciation(calculation, policy)
  - declare_fixed_asset_depreciation_recognition(allocation, period_number, recognition_date, recognition_source_ref)
  - resolve_fixed_asset_depreciation_accounting(recognition_fact)
  - prepare_fixed_asset_depreciation_confirmation(session, accounting_resolution)
  - confirm_fixed_asset_depreciation(snapshot)
  - create_fixed_asset_depreciation_posting_instruction(confirmed_depreciation)
  - execute_fixed_asset_depreciation_posting(instruction)
  - execute_fixed_asset_depreciation_posting_once(instruction)
  - load_fixed_asset_depreciation_posting(session, fixed_asset_id, period_number)
  - execute_fixed_asset_acquisition_posting_once(instruction)
  - load_fixed_asset_acquisition_posting(session, fixed_asset_id)
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
from . import fiscal_posting_audit_read as _fiscal_posting_audit_read
from . import entity_repository as _entity_repository
from . import third_party_repository as _third_party_repository
from . import document_reference_repository as _document_reference_repository
from . import cfdi_metadata_repository as _cfdi_metadata_repository
from . import analytical_dimension_repository as _analytical_dimension_repository
from . import fixed_asset_repository as _fixed_asset_repository
from . import fixed_asset_depreciation as _fixed_asset_depreciation
from . import fixed_asset_depreciation_allocation as _fixed_asset_depreciation_allocation
from . import fixed_asset_depreciation_recognition as _fixed_asset_depreciation_recognition
from . import fixed_asset_depreciation_accounting as _fixed_asset_depreciation_accounting
from . import fixed_asset_depreciation_confirmation as _fixed_asset_depreciation_confirmation


def create_entity(session, entity):
    """Persist one explicit accounting Entity aggregate."""
    return _entity_repository.create_entity(session, entity)


def get_active_entity(session):
    """Return the one active accounting Entity, or None before setup."""
    return _entity_repository.load_active_entity(session)


def register_fiscal_profile(session, profile):
    """Persist one explicit effective-dated fiscal profile interval."""
    return _entity_repository.register_fiscal_profile(session, profile)


def get_fiscal_profile_for_date(session, entity_id, effective_date):
    """Resolve one Entity fiscal profile for an explicit effective date."""
    return _entity_repository.resolve_fiscal_profile(
        session,
        entity_id,
        effective_date,
    )


def create_third_party(session, third_party):
    """Persist one explicit counterparty through the ThirdParty authority."""
    return _third_party_repository.create_third_party(session, third_party)


def get_third_party(session, entity_id, third_party_id):
    """Load one Entity-scoped ThirdParty."""
    return _third_party_repository.get_third_party(
        session,
        entity_id,
        third_party_id,
    )


def list_third_parties(session, entity_id, include_inactive=False):
    """List deterministic Entity-scoped counterparties."""
    return _third_party_repository.list_third_parties(
        session,
        entity_id,
        include_inactive,
    )


def set_third_party_active(session, entity_id, third_party_id, is_active):
    """Activate or deactivate one ThirdParty without deleting its identity."""
    return _third_party_repository.set_third_party_active(
        session,
        entity_id,
        third_party_id,
        is_active,
    )


def create_document_reference(session, document_reference):
    """Persist structured source evidence for one existing journal entry."""
    return _document_reference_repository.create_document_reference(
        session,
        document_reference,
    )


def get_document_reference(session, document_reference_id):
    """Load one structured source-document reference by identity."""
    return _document_reference_repository.get_document_reference(
        session,
        document_reference_id,
    )


def list_document_references(session, entry_id):
    """List deterministic structured source evidence for one journal entry."""
    return _document_reference_repository.list_document_references(
        session,
        entry_id,
    )


def register_cfdi_import_metadata(session, metadata):
    """Persist explicit imported CFDI provenance for one document reference."""
    return _cfdi_metadata_repository.register_cfdi_import_metadata(
        session,
        metadata,
    )


def get_cfdi_import_metadata(session, document_reference_id):
    """Load imported CFDI provenance for one document reference."""
    return _cfdi_metadata_repository.get_cfdi_import_metadata(
        session,
        document_reference_id,
    )


def create_analytical_dimension(session, dimension):
    """Persist one explicit analytical axis through its authority."""
    return _analytical_dimension_repository.create_analytical_dimension(
        session,
        dimension,
    )


def get_analytical_dimension(session, entity_id, dimension_id):
    """Load one Entity-scoped analytical axis."""
    return _analytical_dimension_repository.get_analytical_dimension(
        session,
        entity_id,
        dimension_id,
    )


def list_analytical_dimensions(session, entity_id):
    """List deterministic Entity-scoped analytical axes."""
    return _analytical_dimension_repository.list_analytical_dimensions(
        session,
        entity_id,
    )


def create_analytical_dimension_value(session, dimension_value):
    """Persist one explicit value under an analytical axis."""
    return _analytical_dimension_repository.create_analytical_dimension_value(
        session,
        dimension_value,
    )


def list_analytical_dimension_values(session, dimension_id):
    """List deterministic values for one analytical axis."""
    return _analytical_dimension_repository.list_analytical_dimension_values(
        session,
        dimension_id,
    )


def assign_analytical_dimension_value(session, journal_line_id, dimension_value_id):
    """Attach one explicit analytical value to one existing ledger line."""
    return _analytical_dimension_repository.assign_analytical_dimension_value(
        session,
        journal_line_id,
        dimension_value_id,
    )


def list_journal_line_analytics(session, journal_line_id):
    """List analytical assignments for one existing ledger line."""
    return _analytical_dimension_repository.list_journal_line_analytics(
        session,
        journal_line_id,
    )


def create_fixed_asset(session, fixed_asset):
    """Persist one explicit canonical fixed-asset registry record."""
    return _fixed_asset_repository.create_fixed_asset(session, fixed_asset)


def get_fixed_asset(session, entity_id, fixed_asset_id):
    """Load one Entity-scoped canonical fixed asset."""
    return _fixed_asset_repository.get_fixed_asset(
        session,
        entity_id,
        fixed_asset_id,
    )


def list_fixed_assets(session, entity_id, include_inactive=False):
    """List deterministic Entity-scoped canonical fixed assets."""
    return _fixed_asset_repository.list_fixed_assets(
        session,
        entity_id,
        include_inactive,
    )


def set_fixed_asset_active(session, entity_id, fixed_asset_id, is_active):
    """Activate or deactivate one fixed asset without deleting its identity."""
    return _fixed_asset_repository.set_fixed_asset_active(
        session,
        entity_id,
        fixed_asset_id,
        is_active,
    )


def calculate_fixed_asset_monthly_depreciation(fixed_asset):
    """Delegate exact monthly depreciation calculation."""
    return _fixed_asset_depreciation.calculate_monthly_straight_line_depreciation(
        fixed_asset
    )


def allocate_fixed_asset_monthly_depreciation(calculation, policy):
    """Delegate exact ordinal depreciation monetary allocation."""
    return _fixed_asset_depreciation_allocation.allocate_monthly_depreciation(
        calculation,
        policy,
    )


def declare_fixed_asset_depreciation_recognition(
    allocation,
    period_number,
    recognition_date,
    recognition_source_ref,
):
    """Delegate explicit dated depreciation recognition."""
    return _fixed_asset_depreciation_recognition.declare_fixed_asset_depreciation_recognition(
        allocation,
        period_number,
        recognition_date,
        recognition_source_ref,
    )


def resolve_fixed_asset_depreciation_accounting(recognition_fact):
    """Delegate semantic depreciation accounting resolution."""
    return _fixed_asset_depreciation_accounting.resolve_fixed_asset_depreciation_accounting(
        recognition_fact
    )


def prepare_fixed_asset_depreciation_confirmation(session, accounting_resolution):
    """Delegate configured depreciation confirmation preparation."""
    return _fixed_asset_depreciation_confirmation.prepare_fixed_asset_depreciation_confirmation(
        session,
        accounting_resolution,
    )


def confirm_fixed_asset_depreciation(snapshot):
    """Delegate explicit depreciation confirmation."""
    return _fixed_asset_depreciation_confirmation.confirm_fixed_asset_depreciation(snapshot)


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


def load_fiscal_posting_audit_snapshot(session, entry_id):
    """Load one persisted fiscal audit snapshot using exactly the supplied session."""
    return _fiscal_posting_audit_read.load_fiscal_posting_audit_snapshot(
        session,
        entry_id,
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


from . import fixed_asset_depreciation_posting as _fixed_asset_depreciation_posting
from . import fixed_asset_depreciation_persistence as _fixed_asset_depreciation_persistence


def create_fixed_asset_depreciation_posting_instruction(confirmed_depreciation):
    return _fixed_asset_depreciation_posting.create_fixed_asset_depreciation_posting_instruction(
        confirmed_depreciation
    )


def execute_fixed_asset_depreciation_posting(instruction):
    return _fixed_asset_depreciation_posting.execute_fixed_asset_depreciation_posting(instruction)


def execute_fixed_asset_depreciation_posting_once(instruction):
    """Persist one confirmed depreciation period atomically and at most once."""
    return _fixed_asset_depreciation_persistence.execute_fixed_asset_depreciation_posting_once(
        instruction
    )


def load_fixed_asset_depreciation_posting(session, fixed_asset_id, period_number):
    """Load one persisted depreciation-period identity through its authority."""
    return _fixed_asset_depreciation_persistence.load_fixed_asset_depreciation_posting(
        session,
        fixed_asset_id,
        period_number,
    )


from . import fixed_asset_book_state as _fixed_asset_book_state


def get_fixed_asset_book_state(session, entity_id, fixed_asset_id, as_of=None):
    """Load one canonical recognized fixed-asset book-state projection."""
    return _fixed_asset_book_state.load_fixed_asset_book_state(
        session,
        entity_id,
        fixed_asset_id,
        as_of,
    )


from . import fixed_asset_acquisition as _fixed_asset_acquisition


def create_fixed_asset_acquisition_fact(fixed_asset, asset_class, settlement_method):
    return _fixed_asset_acquisition.create_fixed_asset_acquisition_fact(
        fixed_asset,
        asset_class,
        settlement_method,
    )


def resolve_fixed_asset_acquisition_accounting(acquisition_fact):
    return _fixed_asset_acquisition.resolve_fixed_asset_acquisition_accounting(
        acquisition_fact
    )


from . import fixed_asset_acquisition_confirmation as _fixed_asset_acquisition_confirmation
from . import fixed_asset_acquisition_posting as _fixed_asset_acquisition_posting


def prepare_fixed_asset_acquisition_confirmation(session, accounting_resolution):
    return _fixed_asset_acquisition_confirmation.prepare_fixed_asset_acquisition_confirmation(
        session,
        accounting_resolution,
    )


def confirm_fixed_asset_acquisition(snapshot):
    return _fixed_asset_acquisition_confirmation.confirm_fixed_asset_acquisition(snapshot)


def create_fixed_asset_acquisition_posting_instruction(confirmed_acquisition):
    return _fixed_asset_acquisition_posting.create_fixed_asset_acquisition_posting_instruction(
        confirmed_acquisition
    )


def execute_fixed_asset_acquisition_posting(instruction):
    return _fixed_asset_acquisition_posting.execute_fixed_asset_acquisition_posting(instruction)


from . import fixed_asset_acquisition_persistence as _fixed_asset_acquisition_persistence


def execute_fixed_asset_acquisition_posting_once(instruction):
    """Persist one confirmed fixed-asset acquisition atomically and at most once."""
    return _fixed_asset_acquisition_persistence.execute_fixed_asset_acquisition_posting_once(
        instruction
    )


def load_fixed_asset_acquisition_posting(session, fixed_asset_id):
    """Load one persisted fixed-asset acquisition identity through its authority."""
    return _fixed_asset_acquisition_persistence.load_fixed_asset_acquisition_posting(
        session,
        fixed_asset_id,
    )


from . import user_knowledge_state_repository as _user_knowledge_state_repository


def create_user_knowledge_state(session, state):
    """Persist the one local owner's explicit pedagogical and presentation state."""
    return _user_knowledge_state_repository.create_user_knowledge_state(session, state)


def get_user_knowledge_state(session):
    """Load the local owner's explicit pedagogical and presentation state."""
    return _user_knowledge_state_repository.get_user_knowledge_state(session)


def update_user_knowledge_state(session, state):
    """Update the one local owner's explicit pedagogical and presentation state."""
    return _user_knowledge_state_repository.update_user_knowledge_state(session, state)


from . import explanation as _explanation


def build_economic_fact_explanation(accounting_resolution):
    """Project existing accounting provenance into structured explanation data."""
    return _explanation.build_economic_fact_explanation(accounting_resolution)


from . import explanation_presentation as _explanation_presentation


def plan_explanation_presentation(explanation, user_state):
    """Delegate adaptive explanation-presentation planning to its pure authority."""
    return _explanation_presentation.plan_explanation_presentation(explanation, user_state)


from . import explanation_progression as _explanation_progression


def record_explanation_presentation(session, presentation_plan):
    """Record concepts from one completed presentation."""
    state = _user_knowledge_state_repository.get_user_knowledge_state(session)
    if state is None:
        raise LookupError("user knowledge state has not been initialized")
    updated = _explanation_progression.record_presented_concepts(
        state,
        presentation_plan,
    )
    return _user_knowledge_state_repository.update_user_knowledge_state(
        session,
        updated,
    )


from . import topic_learning as _topic_learning


def record_user_topic_learning(session, topic, learned_at):
    """Persist one explicit topic-learning acknowledgement."""
    state = _user_knowledge_state_repository.get_user_knowledge_state(session)
    if state is None:
        raise LookupError("user knowledge state has not been initialized")
    updated = _topic_learning.record_learned_topic(state, topic, learned_at)
    return _user_knowledge_state_repository.update_user_knowledge_state(
        session,
        updated,
    )


from . import explanation_request as _explanation_request


def plan_requested_explanation(explanation, user_state):
    """Delegate one-shot requested explanation planning to its pure authority."""
    return _explanation_request.plan_requested_explanation(explanation, user_state)


from . import explanation_view as _explanation_view


def build_explanation_presentation_view(explanation, presentation_plan):
    """Delegate structured explanation view selection."""
    return _explanation_view.build_explanation_presentation_view(
        explanation,
        presentation_plan,
    )


from . import explanation_delivery as _explanation_delivery


def prepare_explanation_presentation(accounting_resolution, user_state):
    """Delegate standard explanation delivery."""
    return _explanation_delivery.prepare_explanation_presentation(
        accounting_resolution,
        user_state,
    )


def prepare_requested_explanation_presentation(accounting_resolution, user_state):
    """Delegate requested explanation delivery."""
    return _explanation_delivery.prepare_requested_explanation_presentation(
        accounting_resolution,
        user_state,
    )


from . import program_repository as _program_repository


def create_program(session, program):
    """Persist one explicit OSC Program through its authority."""
    return _program_repository.create_program(session, program)


def get_program(session, entity_id, program_id):
    """Load one Entity-scoped Program through its authority."""
    return _program_repository.get_program(session, entity_id, program_id)


def list_programs(session, entity_id):
    """List deterministic Entity-scoped Programs through their authority."""
    return _program_repository.list_programs(session, entity_id)
