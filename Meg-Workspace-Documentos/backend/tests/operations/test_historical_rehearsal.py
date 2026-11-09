"""Operator safety boundaries; the real PostgreSQL rehearsal runs in CI."""
import os
import subprocess
import sys

import pytest
from psycopg2 import extensions

from scripts.postgres_backup import BackupInputError
from scripts.rehearse_historical_backup import compare, projection_query, validate_target


@pytest.mark.parametrize('database', ['megalodon', 'postgres', 'megalodon_rehearsal_', 'megalodon_rehearsal_bad-name'])
def test_target_rejects_every_non_rehearsal_database(database):
    with pytest.raises(BackupInputError, match='dedicated'):
        validate_target(f'postgresql://user:private@localhost/{database}')


def test_target_translates_driver_and_preserves_encoded_credentials():
    value = validate_target('postgresql+psycopg2://u:secret%40value@localhost/megalodon_rehearsal_real?sslmode=require')
    assert value == 'postgresql+asyncpg://u:secret%40value@localhost/megalodon_rehearsal_real?sslmode=require'


def test_hash_comparison_detects_a_changed_unselected_table_and_duplicate_count():
    before = {'documentos': {'rows': 2, 'historical_columns_sha256': 'abc'}}
    for after in ({'documentos': {'rows': 1, 'historical_columns_sha256': 'abc'}},
                  {'documentos': {'rows': 2, 'historical_columns_sha256': 'def'}}, {}):
        with pytest.raises(BackupInputError, match='preservation failed'):
            compare(before, after)
    compare(before, before)


def test_projection_renames_authors_and_converts_only_known_naive_utc(monkeypatch):
    # Rendering identifiers needs only libpq's quoting function, no server. The
    # PostgreSQL job executes these projections against populated real tables.
    monkeypatch.setattr(extensions, 'quote_ident', lambda value, context: '"' + value.replace('"', '""') + '"')
    old = projection_query('snapshots', [('created_at', 'timestamp without time zone')]).as_string(None)
    new = projection_query('snapshots', [('created_at', 'timestamp without time zone')], migrated=True).as_string(None)
    authors = projection_query('catalog_terms', [('created_by_id', 'uuid')], migrated=True).as_string(None)
    other = projection_query('documentos', [('created_at', 'timestamp without time zone')]).as_string(None)
    assert "AT TIME ZONE 'UTC'" in old and 'AT TIME ZONE' not in new
    assert '"creado_por_id"::text AS "created_by_id"' in authors
    assert 'AT TIME ZONE' not in other
    injected = projection_query('a"; DROP TABLE users; --', [('a"b', 'text')]).as_string(None)
    assert '"a""; DROP TABLE users; --"' in injected and '"a""b"' in injected


def test_command_rejects_live_database_without_connecting_or_leaking_password(tmp_path):
    report = tmp_path / 'report.json'
    backup = tmp_path / 'controlled.dump'
    backup.write_bytes(b'not used')
    result = subprocess.run([sys.executable, '-m', 'scripts.rehearse_historical_backup',
                             '--backup', str(backup), '--report', str(report)],
                            env=dict(os.environ, DATABASE_URL='postgresql://u:secret-to-hide@localhost/megalodon'),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and 'dedicated' in result.stderr
    assert 'secret-to-hide' not in result.stderr + result.stdout
    assert not report.exists()


def test_command_never_overwrites_an_existing_report_or_backup(tmp_path):
    existing = tmp_path / 'existing'
    existing.write_bytes(b'original private file')
    result = subprocess.run([sys.executable, '-m', 'scripts.rehearse_historical_backup',
                             '--backup', str(existing), '--report', str(existing)],
                            env=dict(os.environ, DATABASE_URL='postgresql://u:secret-to-hide@localhost/megalodon_rehearsal_test'),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and existing.read_bytes() == b'original private file'
    assert 'secret-to-hide' not in result.stderr + result.stdout
