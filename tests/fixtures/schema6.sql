-- Frozen schema 6 DDL: models.py at main 9c4a9882d47c327c02a096be1e38f96fa1b90f7e.
-- No runtime metadata imports; no historical data or AQR-006 structures.
BEGIN TRANSACTION;
CREATE TABLE account (
	id INTEGER NOT NULL, 
	code VARCHAR, 
	name VARCHAR NOT NULL, 
	nature VARCHAR NOT NULL, 
	vat_flag BOOLEAN NOT NULL, 
	origin VARCHAR NOT NULL, 
	parent_id INTEGER, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(parent_id) REFERENCES account (id)
);
CREATE TABLE accountingcalendar (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	activity_start VARCHAR NOT NULL, 
	declaration_json VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (entity_id), 
	FOREIGN KEY(entity_id) REFERENCES entity (id), 
	CONSTRAINT ck_calendar_singleton CHECK (id = 1)
);
CREATE TABLE accountingperiod (
	id INTEGER NOT NULL, 
	year INTEGER NOT NULL, 
	month INTEGER NOT NULL, 
	start_date VARCHAR NOT NULL, 
	end_date VARCHAR NOT NULL, 
	state VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_period_state CHECK (state IN ('open', 'closed')), 
	FOREIGN KEY(year) REFERENCES fiscalyear (year), 
	CONSTRAINT uq_period_month UNIQUE (year, month)
);
CREATE TABLE accountrolebinding (
	id INTEGER NOT NULL, 
	role VARCHAR NOT NULL, 
	account_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (role), 
	FOREIGN KEY(account_id) REFERENCES account (id)
);
CREATE TABLE analyticaldimension (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	"key" VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_analytical_dimension_entity_key UNIQUE (entity_id, "key"), 
	FOREIGN KEY(entity_id) REFERENCES entity (id)
);
CREATE TABLE analyticaldimensionvalue (
	id INTEGER NOT NULL, 
	dimension_id INTEGER NOT NULL, 
	code VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_analytical_dimension_value_code UNIQUE (dimension_id, code), 
	FOREIGN KEY(dimension_id) REFERENCES analyticaldimension (id)
);
CREATE TABLE appconfig (
	id INTEGER NOT NULL, 
	"key" VARCHAR NOT NULL, 
	value VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE asset (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	value VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE auditevent (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	event_type VARCHAR NOT NULL, 
	timestamp TEXT NOT NULL, 
	details_json TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entity_id) REFERENCES entity (id)
);
CREATE TABLE cfdiimportmetadata (
	id INTEGER NOT NULL, 
	document_reference_id INTEGER NOT NULL, 
	cfdi_version VARCHAR NOT NULL, 
	uuid VARCHAR NOT NULL, 
	issuer_rfc VARCHAR NOT NULL, 
	receiver_rfc VARCHAR NOT NULL, 
	issued_at VARCHAR NOT NULL, 
	stamped_at VARCHAR NOT NULL, 
	sello_sat TEXT NOT NULL, 
	sat_certificate_number VARCHAR NOT NULL, 
	imported_at VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_reference_id) REFERENCES documentreference (id)
);
CREATE TABLE documentreference (
	id INTEGER NOT NULL, 
	entry_id INTEGER NOT NULL, 
	third_party_id INTEGER, 
	document_type VARCHAR NOT NULL, 
	document_number VARCHAR NOT NULL, 
	issuer_name VARCHAR, 
	date VARCHAR NOT NULL, 
	file_hash VARCHAR, 
	file_path TEXT, 
	external_url TEXT, 
	is_validated BOOLEAN NOT NULL, 
	validation_notes TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(third_party_id) REFERENCES thirdparty (id), 
	FOREIGN KEY(entry_id) REFERENCES journalentry (id)
);
CREATE TABLE donation (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	date TEXT NOT NULL, 
	amount TEXT NOT NULL, 
	donor_third_party_id INTEGER, 
	purpose TEXT, 
	is_restricted BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entity_id) REFERENCES entity (id), 
	FOREIGN KEY(donor_third_party_id) REFERENCES thirdparty (id)
);
CREATE TABLE entity (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	rfc VARCHAR, 
	legal_personality VARCHAR NOT NULL, 
	legal_form VARCHAR NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE entityprofile (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	economic_purpose VARCHAR NOT NULL, 
	is_donor_authorized BOOLEAN NOT NULL, 
	special_capabilities_json TEXT NOT NULL, 
	modules_enabled_json TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entity_id) REFERENCES entity (id)
);
CREATE TABLE fiscalpostingauditeffectrecord (
	id INTEGER NOT NULL, 
	audit_record_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	rule_key VARCHAR NOT NULL, 
	base VARCHAR NOT NULL, 
	rate VARCHAR NOT NULL, 
	unit VARCHAR NOT NULL, 
	rule_effective_from DATE NOT NULL, 
	rule_effective_to DATE, 
	rule_source_ref VARCHAR NOT NULL, 
	exact_fiscal_amount VARCHAR NOT NULL, 
	rounding_policy_key VARCHAR NOT NULL, 
	rounding_quantizer VARCHAR NOT NULL, 
	rounding_mode VARCHAR NOT NULL, 
	rounding_source_ref VARCHAR NOT NULL, 
	rounded_fiscal_amount VARCHAR NOT NULL, 
	fiscal_role VARCHAR NOT NULL, 
	fiscal_side VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_fiscal_posting_audit_effect_position UNIQUE (audit_record_id, position), 
	FOREIGN KEY(audit_record_id) REFERENCES fiscalpostingauditrecord (id)
);
CREATE TABLE fiscalpostingauditrecord (
	id INTEGER NOT NULL, 
	entry_id INTEGER NOT NULL, 
	fact_type VARCHAR NOT NULL, 
	fact_amount VARCHAR NOT NULL, 
	payment_method VARCHAR NOT NULL, 
	effective_date DATE NOT NULL, 
	jurisdiction VARCHAR NOT NULL, 
	regime VARCHAR NOT NULL, 
	entity_type VARCHAR NOT NULL, 
	rule_key VARCHAR NOT NULL, 
	base VARCHAR NOT NULL, 
	rate VARCHAR NOT NULL, 
	unit VARCHAR NOT NULL, 
	rule_effective_from DATE NOT NULL, 
	rule_effective_to DATE, 
	rule_source_ref VARCHAR NOT NULL, 
	exact_fiscal_amount VARCHAR NOT NULL, 
	rounding_policy_key VARCHAR NOT NULL, 
	rounding_quantizer VARCHAR NOT NULL, 
	rounding_mode VARCHAR NOT NULL, 
	rounding_source_ref VARCHAR NOT NULL, 
	rounded_fiscal_amount VARCHAR NOT NULL, 
	amount_basis VARCHAR NOT NULL, 
	adjustment_role VARCHAR NOT NULL, 
	fiscal_role VARCHAR NOT NULL, 
	fiscal_side VARCHAR NOT NULL, 
	zero_fiscal_line_policy VARCHAR NOT NULL, 
	omitted_zero_account_role VARCHAR, 
	omitted_zero_account_id INTEGER, 
	omitted_zero_account_code VARCHAR, 
	omitted_zero_account_name VARCHAR, 
	omitted_zero_side VARCHAR, 
	omitted_zero_amount VARCHAR, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entry_id) REFERENCES journalentry (id)
);
CREATE TABLE fiscalprofile (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	jurisdiction VARCHAR NOT NULL, 
	fiscal_regime_code VARCHAR NOT NULL, 
	tax_characteristics_json TEXT NOT NULL, 
	effective_from DATE NOT NULL, 
	effective_to DATE, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entity_id) REFERENCES entity (id), 
	CONSTRAINT uq_fiscal_profile_entity_start UNIQUE (entity_id, effective_from)
);
CREATE TABLE fiscalruleversion (
	id INTEGER NOT NULL, 
	rule_key VARCHAR NOT NULL, 
	jurisdiction VARCHAR NOT NULL, 
	regime VARCHAR NOT NULL, 
	entity_type VARCHAR NOT NULL, 
	effective_from DATE NOT NULL, 
	effective_to DATE, 
	value VARCHAR NOT NULL, 
	unit VARCHAR NOT NULL, 
	source_ref VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_fiscal_rule_scope_start UNIQUE (rule_key, jurisdiction, regime, entity_type, effective_from)
);
CREATE TABLE fiscalyear (
	year INTEGER NOT NULL, 
	calendar_id INTEGER NOT NULL, 
	start_date VARCHAR NOT NULL, 
	end_date VARCHAR NOT NULL, 
	state VARCHAR NOT NULL, 
	closing_entry_id INTEGER, 
	PRIMARY KEY (year), 
	CONSTRAINT ck_year_state CHECK (state IN ('open', 'closed')), 
	FOREIGN KEY(calendar_id) REFERENCES accountingcalendar (id), 
	FOREIGN KEY(closing_entry_id) REFERENCES journalentry (id)
);
CREATE TABLE fixedasset (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	code VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	acquisition_date DATE NOT NULL, 
	in_service_date DATE NOT NULL, 
	acquisition_cost TEXT NOT NULL, 
	residual_value TEXT NOT NULL, 
	useful_life_months INTEGER NOT NULL, 
	depreciation_method VARCHAR NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_fixed_asset_entity_code UNIQUE (entity_id, code), 
	FOREIGN KEY(entity_id) REFERENCES entity (id)
);
CREATE TABLE fixedassetacquisitionpostingrecord (
	id INTEGER NOT NULL, 
	fixed_asset_id INTEGER NOT NULL, 
	entry_id INTEGER NOT NULL, 
	asset_class VARCHAR NOT NULL, 
	settlement_method VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entry_id) REFERENCES journalentry (id), 
	CONSTRAINT uq_fixed_asset_acquisition_asset UNIQUE (fixed_asset_id), 
	CONSTRAINT uq_fixed_asset_acquisition_entry UNIQUE (entry_id), 
	FOREIGN KEY(fixed_asset_id) REFERENCES fixedasset (id)
);
CREATE TABLE fixedassetdepreciationpostingrecord (
	id INTEGER NOT NULL, 
	fixed_asset_id INTEGER NOT NULL, 
	period_number INTEGER NOT NULL, 
	entry_id INTEGER NOT NULL, 
	recognition_source_ref VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entry_id) REFERENCES journalentry (id), 
	CONSTRAINT uq_fixed_asset_depreciation_period UNIQUE (fixed_asset_id, period_number), 
	FOREIGN KEY(fixed_asset_id) REFERENCES fixedasset (id)
);
CREATE TABLE journalentry (
	id INTEGER NOT NULL, 
	date DATETIME NOT NULL, 
	concept VARCHAR, 
	doc_ref VARCHAR, 
	period_id INTEGER, 
	posted_by VARCHAR, 
	state VARCHAR NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE journalentryreversal (
	id INTEGER NOT NULL, 
	original_entry_id INTEGER NOT NULL, 
	reversal_entry_id INTEGER NOT NULL, 
	reason TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_reversal_original UNIQUE (original_entry_id), 
	FOREIGN KEY(original_entry_id) REFERENCES journalentry (id), 
	FOREIGN KEY(reversal_entry_id) REFERENCES journalentry (id)
);
CREATE TABLE journalline (
	id INTEGER NOT NULL, 
	entry_id INTEGER, 
	account_code VARCHAR, 
	account_id INTEGER, 
	debit VARCHAR NOT NULL, 
	credit VARCHAR NOT NULL, 
	description VARCHAR, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE journallineanalyticaldimension (
	id INTEGER NOT NULL, 
	journal_line_id INTEGER NOT NULL, 
	dimension_id INTEGER NOT NULL, 
	dimension_value_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(journal_line_id) REFERENCES journalline (id), 
	CONSTRAINT uq_journal_line_analytical_dimension UNIQUE (journal_line_id, dimension_id), 
	FOREIGN KEY(dimension_value_id) REFERENCES analyticaldimensionvalue (id), 
	FOREIGN KEY(dimension_id) REFERENCES analyticaldimension (id)
);
CREATE TABLE program (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	description TEXT, 
	budget TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entity_id) REFERENCES entity (id)
);
CREATE TABLE thirdparty (
	id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	rfc VARCHAR, 
	email VARCHAR, 
	phone VARCHAR, 
	party_type VARCHAR NOT NULL, 
	address VARCHAR, 
	contact_person VARCHAR, 
	notes TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(entity_id) REFERENCES entity (id)
);
CREATE TABLE userknowledgestate (
	id INTEGER NOT NULL, 
	explanation_level VARCHAR NOT NULL, 
	concepts_seen_json TEXT NOT NULL, 
	ui_language VARCHAR NOT NULL, 
	decimal_separator VARCHAR NOT NULL, 
	currency_symbol VARCHAR NOT NULL, 
	preferred_report_format VARCHAR NOT NULL, 
	always_show_professional_view BOOLEAN NOT NULL, 
	learned_topics_json TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_user_knowledge_state_singleton CHECK (id = 1)
);
CREATE INDEX ix_account_parent_id ON account (parent_id);
CREATE UNIQUE INDEX uq_entity_single_active ON entity (is_active) WHERE is_active = 1;
CREATE INDEX ix_fiscalruleversion_effective_from ON fiscalruleversion (effective_from);
CREATE INDEX ix_fiscalruleversion_regime ON fiscalruleversion (regime);
CREATE INDEX ix_fiscalruleversion_effective_to ON fiscalruleversion (effective_to);
CREATE INDEX ix_fiscalruleversion_entity_type ON fiscalruleversion (entity_type);
CREATE INDEX ix_fiscalruleversion_rule_key ON fiscalruleversion (rule_key);
CREATE INDEX ix_fiscalruleversion_jurisdiction ON fiscalruleversion (jurisdiction);
CREATE INDEX ix_accountrolebinding_account_id ON accountrolebinding (account_id);
CREATE INDEX ix_fixedasset_in_service_date ON fixedasset (in_service_date);
CREATE INDEX ix_fixedasset_acquisition_date ON fixedasset (acquisition_date);
CREATE INDEX ix_fixedasset_entity_id ON fixedasset (entity_id);
CREATE INDEX ix_fixedasset_is_active ON fixedasset (is_active);
CREATE INDEX ix_analyticaldimension_entity_id ON analyticaldimension (entity_id);
CREATE UNIQUE INDEX ix_entityprofile_entity_id ON entityprofile (entity_id);
CREATE INDEX ix_fiscalprofile_effective_from ON fiscalprofile (effective_from);
CREATE INDEX ix_fiscalprofile_effective_to ON fiscalprofile (effective_to);
CREATE INDEX ix_fiscalprofile_entity_id ON fiscalprofile (entity_id);
CREATE INDEX ix_thirdparty_party_type ON thirdparty (party_type);
CREATE INDEX ix_thirdparty_is_active ON thirdparty (is_active);
CREATE INDEX ix_thirdparty_entity_id ON thirdparty (entity_id);
CREATE UNIQUE INDEX ix_journalentryreversal_reversal_entry_id ON journalentryreversal (reversal_entry_id);
CREATE INDEX ix_journalentryreversal_original_entry_id ON journalentryreversal (original_entry_id);
CREATE UNIQUE INDEX ix_fiscalpostingauditrecord_entry_id ON fiscalpostingauditrecord (entry_id);
CREATE INDEX ix_program_entity_id ON program (entity_id);
CREATE INDEX ix_auditevent_entity_id ON auditevent (entity_id);
CREATE INDEX ix_auditevent_event_type ON auditevent (event_type);
CREATE INDEX ix_auditevent_timestamp ON auditevent (timestamp);
CREATE INDEX ix_analyticaldimensionvalue_dimension_id ON analyticaldimensionvalue (dimension_id);
CREATE INDEX ix_fixedassetdepreciationpostingrecord_entry_id ON fixedassetdepreciationpostingrecord (entry_id);
CREATE INDEX ix_fixedassetdepreciationpostingrecord_fixed_asset_id ON fixedassetdepreciationpostingrecord (fixed_asset_id);
CREATE INDEX ix_documentreference_entry_id ON documentreference (entry_id);
CREATE INDEX ix_documentreference_third_party_id ON documentreference (third_party_id);
CREATE INDEX ix_documentreference_date ON documentreference (date);
CREATE INDEX ix_documentreference_document_type ON documentreference (document_type);
CREATE INDEX ix_documentreference_is_validated ON documentreference (is_validated);
CREATE INDEX ix_fiscalpostingauditeffectrecord_position ON fiscalpostingauditeffectrecord (position);
CREATE INDEX ix_fiscalpostingauditeffectrecord_audit_record_id ON fiscalpostingauditeffectrecord (audit_record_id);
CREATE INDEX ix_fixedassetacquisitionpostingrecord_entry_id ON fixedassetacquisitionpostingrecord (entry_id);
CREATE INDEX ix_fixedassetacquisitionpostingrecord_fixed_asset_id ON fixedassetacquisitionpostingrecord (fixed_asset_id);
CREATE INDEX ix_donation_donor_third_party_id ON donation (donor_third_party_id);
CREATE INDEX ix_donation_date ON donation (date);
CREATE INDEX ix_donation_entity_id ON donation (entity_id);
CREATE UNIQUE INDEX ix_cfdiimportmetadata_uuid ON cfdiimportmetadata (uuid);
CREATE UNIQUE INDEX ix_cfdiimportmetadata_document_reference_id ON cfdiimportmetadata (document_reference_id);
CREATE INDEX ix_journallineanalyticaldimension_dimension_value_id ON journallineanalyticaldimension (dimension_value_id);
CREATE INDEX ix_journallineanalyticaldimension_dimension_id ON journallineanalyticaldimension (dimension_id);
CREATE INDEX ix_journallineanalyticaldimension_journal_line_id ON journallineanalyticaldimension (journal_line_id);
COMMIT;
PRAGMA user_version=6;
