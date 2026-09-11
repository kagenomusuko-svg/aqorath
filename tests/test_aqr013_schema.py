import sqlite3


def test_schema_12_to_13_adds_only_custom_package_configuration(tmp_path):
    from aqorath import migrations
    from test_aqr010_cfdi_source import _schema10_snapshot

    path = tmp_path / "historical-v12.db"
    _schema10_snapshot(path)
    migrations._migrate_10_to_11(path)
    migrations._migrate_11_to_12(path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 12")
        before = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        conn.commit()

    result = migrations.migrate_database(path)
    assert result["from_version"] == 12
    assert result["to_version"] == 13

    with sqlite3.connect(path) as conn:
        after = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert before <= after
        assert after - before == {"customreportpackage"}
        assert conn.execute("SELECT COUNT(*) FROM customreportpackage").fetchone()[0] == 0
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 13

        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(customreportpackage)")
        }
        assert columns == {
            "id",
            "entity_id",
            "name",
            "report_definition_ids_json",
            "created_at",
        }
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='customreportpackage'"
        ).fetchone()[0].lower()
        for forbidden in (
            "balance",
            "debit",
            "credit",
            "amount",
            "result",
            "rendered_output",
        ):
            assert forbidden not in table_sql
