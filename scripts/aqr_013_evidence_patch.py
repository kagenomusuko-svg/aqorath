from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match in {path}, found {text.count(old)}")
    p.write_text(text.replace(old, new, 1))


path = "aqorath/report_authority_views.py"
replace_once(
    path,
    "from .inventory_models import ProductRecord\nfrom .models import (\n",
    "from .cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord\nfrom .inventory_models import ProductRecord\nfrom .models import (\n",
)
replace_once(
    path,
    "class DocumentEvidence:\n    document_reference_id: int\n    document_type: str\n",
    "class DocumentEvidence:\n    document_reference_id: int\n    cfdi_source_id: int | None\n    document_type: str\n",
)
old = '''        cfdi = session.exec(
            select(CfdiImportMetadataRecord).where(
                CfdiImportMetadataRecord.document_reference_id == document.id
            )
        ).one_or_none()
        result.append(
            DocumentEvidence(
                document_reference_id=document.id,
                document_type=document.document_type,
                document_number=document.document_number,
                issuer_name=document.issuer_name,
                document_date=document.date,
                third_party_id=document.third_party_id,
                is_validated=document.is_validated,
                cfdi_uuid=None if cfdi is None else cfdi.uuid,
                cfdi_version=None if cfdi is None else cfdi.cfdi_version,
            )
        )
'''
new = '''        legacy_cfdi = session.exec(
            select(CfdiImportMetadataRecord).where(
                CfdiImportMetadataRecord.document_reference_id == document.id
            )
        ).one_or_none()
        link = session.exec(
            select(CfdiSourceLinkRecord).where(
                CfdiSourceLinkRecord.document_reference_id == document.id
            )
        ).one_or_none()
        source = None
        if link is not None:
            source = session.get(CfdiSourceRecord, link.cfdi_source_id)
            if source is None:
                raise RuntimeError("CFDI source link references missing AQR-010 source")
        result.append(
            DocumentEvidence(
                document_reference_id=document.id,
                cfdi_source_id=None if source is None else source.id,
                document_type=document.document_type,
                document_number=document.document_number,
                issuer_name=document.issuer_name,
                document_date=document.date,
                third_party_id=document.third_party_id,
                is_validated=document.is_validated,
                cfdi_uuid=(source.uuid if source is not None else (None if legacy_cfdi is None else legacy_cfdi.uuid)),
                cfdi_version=(source.version if source is not None else (None if legacy_cfdi is None else legacy_cfdi.cfdi_version)),
            )
        )
'''
replace_once(path, old, new)

# The initial AQR-013 test was written before the three authority-consumption products were added.
path = "tests/test_aqr013_reporting_engine.py"
replace_once(
    path,
    '''    assert [item.key for item in governance] == [
        "financial.trial_balance.period",
        "financial.income_statement.period",
        "financial.balance_sheet.as_of",
        "professional.journal.period",
        "professional.general_ledger.period",
    ]
    assert len({item.id for item in definitions}) == 5
''',
    '''    assert [item.key for item in governance] == [
        "financial.trial_balance.period",
        "financial.income_statement.period",
        "financial.balance_sheet.as_of",
        "professional.journal.period",
        "professional.general_ledger.period",
        "analytical.activity.period",
        "inventory.valuation.as_of",
        "fiscal.evidence.period",
    ]
    assert len({item.id for item in definitions}) == 8
''',
)

print("AQR-013 evidence/test patch applied")
