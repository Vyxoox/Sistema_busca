import argparse
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / '.env', override=True)

DATE_FIELDS_FUNCIONARIO = {
    'data_nasc',
    'data_ingresso_der',
    'data_inicio',
    'data_admissao',
    'data_desligamento',
}

DATETIME_FIELDS_FUNCIONARIO = {
    'data_criacao',
    'data_atualizacao',
}


def _parse_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    raw = str(value).strip()
    if not raw:
        return None
    raw = raw[:10]
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_datetime(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value

    raw = str(value).strip()
    if not raw:
        return None

    raw = raw.replace('T', ' ')
    if '+' in raw:
        raw = raw.split('+', 1)[0]
    if raw.endswith('Z'):
        raw = raw[:-1]

    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))

    raw = str(value).strip().lower()
    if raw in {'1', 'true', 't', 'yes', 'y'}:
        return True
    if raw in {'0', 'false', 'f', 'no', 'n', ''}:
        return False
    return bool(value)


def _fetch_all_rows(sqlite_conn, table_name):
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    cursor.execute(f'SELECT * FROM {table_name} ORDER BY id')
    return [dict(row) for row in cursor.fetchall()]


def _normalize_usuarios(rows):
    out = []
    for row in rows:
        out.append(
            {
                'id': int(row['id']),
                'login': row['login'],
                'hash_senha': row['hash_senha'],
                'perfil': row['perfil'],
                'permissoes': row['permissoes'],
                'is_admin': _to_bool(row['is_admin']) or False,
                'is_superadmin': _to_bool(row['is_superadmin']) or False,
            }
        )
    return out


def _normalize_funcionarios(rows):
    out = []
    for row in rows:
        clean = dict(row)
        clean['id'] = int(clean['id'])
        clean['ativo'] = _to_bool(clean['ativo'])
        matricula = clean.get('matricula')
        if matricula is None:
            clean['matricula'] = None
        else:
            matricula = str(matricula).strip()
            clean['matricula'] = matricula or None

        for field in DATE_FIELDS_FUNCIONARIO:
            clean[field] = _parse_date(clean.get(field))
        for field in DATETIME_FIELDS_FUNCIONARIO:
            clean[field] = _parse_datetime(clean.get(field))

        out.append(clean)
    return out


def _normalize_logs(rows, user_ids):
    out = []
    for row in rows:
        clean = dict(row)
        clean['id'] = int(clean['id'])
        clean['criado_em'] = _parse_datetime(clean.get('criado_em'))

        usuario_id = clean.get('usuario_id')
        if usuario_id is None:
            clean['usuario_id'] = None
        else:
            usuario_id = int(usuario_id)
            clean['usuario_id'] = usuario_id if usuario_id in user_ids else None

        out.append(clean)
    return out


def _count_target_tables(conn):
    counts = {}
    for table in ('usuarios', 'funcionarios', 'logs_auditoria'):
        counts[table] = conn.execute(text(f'SELECT COUNT(*) FROM dbo.{table}')).scalar_one()
    return counts


def _clear_target(conn):
    conn.execute(text('DELETE FROM dbo.logs_auditoria'))
    conn.execute(text('DELETE FROM dbo.funcionarios'))
    conn.execute(text('DELETE FROM dbo.usuarios'))

    conn.execute(text("DBCC CHECKIDENT ('dbo.logs_auditoria', RESEED, 0)"))
    conn.execute(text("DBCC CHECKIDENT ('dbo.funcionarios', RESEED, 0)"))
    conn.execute(text("DBCC CHECKIDENT ('dbo.usuarios', RESEED, 0)"))


def _ensure_mssql_nullable_unique_matricula(conn):
    if conn.dialect.name != 'mssql':
        return

    conn.execute(
        text(
            """
            DECLARE @schema_name sysname = N'dbo';
            DECLARE @table_name sysname = N'funcionarios';
            DECLARE @column_name sysname = N'matricula';
            DECLARE @target_index_name sysname = N'UX_funcionarios_matricula_not_null';
            DECLARE @sql nvarchar(max);

            SET @sql = N'';
            SELECT @sql = @sql +
                N'ALTER TABLE [' + s.name + N'].[' + t.name + N'] DROP CONSTRAINT [' +
                REPLACE(kc.name, N']', N']]') + N'];'
            FROM sys.key_constraints kc
            JOIN sys.tables t ON t.object_id = kc.parent_object_id
            JOIN sys.schemas s ON s.schema_id = t.schema_id
            JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id
                AND ic.index_id = kc.unique_index_id
            JOIN sys.columns c ON c.object_id = ic.object_id
                AND c.column_id = ic.column_id
            WHERE kc.type = 'UQ'
              AND s.name = @schema_name
              AND t.name = @table_name
              AND c.name = @column_name;

            IF LEN(@sql) > 0
                EXEC sp_executesql @sql;

            SET @sql = N'';
            SELECT @sql = @sql +
                N'DROP INDEX [' + REPLACE(i.name, N']', N']]') + N'] ON [' +
                s.name + N'].[' + t.name + N'];'
            FROM sys.indexes i
            JOIN sys.tables t ON t.object_id = i.object_id
            JOIN sys.schemas s ON s.schema_id = t.schema_id
            JOIN sys.index_columns ic ON ic.object_id = i.object_id
                AND ic.index_id = i.index_id
            JOIN sys.columns c ON c.object_id = ic.object_id
                AND c.column_id = ic.column_id
            WHERE s.name = @schema_name
              AND t.name = @table_name
              AND c.name = @column_name
              AND i.is_unique = 1
              AND i.is_primary_key = 0
              AND i.is_unique_constraint = 0
              AND i.has_filter = 0;

            IF LEN(@sql) > 0
                EXEC sp_executesql @sql;

            IF NOT EXISTS (
                SELECT 1
                FROM sys.indexes i
                JOIN sys.tables t ON t.object_id = i.object_id
                JOIN sys.schemas s ON s.schema_id = t.schema_id
                WHERE s.name = @schema_name
                  AND t.name = @table_name
                  AND i.name = @target_index_name
            )
            BEGIN
                SET @sql = N'CREATE UNIQUE INDEX [' + REPLACE(@target_index_name, N']', N']]') + N'] ' +
                           N'ON [dbo].[funcionarios] ([matricula]) ' +
                           N'WHERE [matricula] IS NOT NULL;';
                EXEC sp_executesql @sql;
            END
            """
        )
    )


def _insert_with_identity(conn, table_name, rows):
    if not rows:
        return 0

    columns = list(rows[0].keys())
    column_sql = ', '.join(f'[{column}]' for column in columns)
    param_sql = ', '.join(f':{column}' for column in columns)

    conn.execute(text(f'SET IDENTITY_INSERT dbo.{table_name} ON'))
    try:
        conn.execute(
            text(f'INSERT INTO dbo.{table_name} ({column_sql}) VALUES ({param_sql})'),
            rows,
        )
    finally:
        conn.execute(text(f'SET IDENTITY_INSERT dbo.{table_name} OFF'))

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description='Migra dados do SQLite para SQL Server.')
    parser.add_argument(
        '--source-sqlite',
        default=str(ROOT_DIR / 'instance' / 'funcionarios.db'),
        help='Caminho do SQLite de origem.',
    )
    parser.add_argument(
        '--target-url',
        default=None,
        help='URL de destino. Se omitido, usa DATABASE_URL do .env.',
    )
    parser.add_argument(
        '--clear-target',
        action='store_true',
        help='Apaga dados atuais do SQL Server antes de importar.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Somente valida/conta sem gravar.',
    )
    args = parser.parse_args()

    source_path = Path(args.source_sqlite)
    if not source_path.exists():
        raise SystemExit(f'Arquivo SQLite nao encontrado: {source_path}')

    target_url = args.target_url or os.getenv('DATABASE_URL')
    if not target_url:
        raise SystemExit('DATABASE_URL nao configurada no ambiente/.env')
    if target_url.lower().startswith('sqlite'):
        raise SystemExit(
            'Destino aponta para SQLite. Configure --target-url com SQL Server '
            'ou ajuste DATABASE_URL no .env.'
        )

    sqlite_conn = sqlite3.connect(source_path)
    source_usuarios = _normalize_usuarios(_fetch_all_rows(sqlite_conn, 'usuarios'))
    source_funcionarios = _normalize_funcionarios(_fetch_all_rows(sqlite_conn, 'funcionarios'))
    user_ids = {row['id'] for row in source_usuarios}
    source_logs = _normalize_logs(_fetch_all_rows(sqlite_conn, 'logs_auditoria'), user_ids)
    sqlite_conn.close()

    print('Origem SQLite:')
    print(f'  usuarios: {len(source_usuarios)}')
    print(f'  funcionarios: {len(source_funcionarios)}')
    print(f'  logs_auditoria: {len(source_logs)}')

    engine = create_engine(target_url, future=True)
    with engine.begin() as conn:
        conn.execute(text('SELECT 1'))

        before = _count_target_tables(conn)
        print('Destino SQL Server (antes):')
        print(f"  usuarios: {before['usuarios']}")
        print(f"  funcionarios: {before['funcionarios']}")
        print(f"  logs_auditoria: {before['logs_auditoria']}")

        if args.dry_run:
            print('Dry-run ativo: nenhuma escrita realizada.')
            return

        if before['usuarios'] or before['funcionarios'] or before['logs_auditoria']:
            if not args.clear_target:
                raise SystemExit(
                    'Destino possui dados. Rode novamente com --clear-target para sobrescrever.'
                )
            _clear_target(conn)

        _ensure_mssql_nullable_unique_matricula(conn)
        _insert_with_identity(conn, 'usuarios', source_usuarios)
        _insert_with_identity(conn, 'funcionarios', source_funcionarios)
        _insert_with_identity(conn, 'logs_auditoria', source_logs)

        after = _count_target_tables(conn)
        print('Destino SQL Server (depois):')
        print(f"  usuarios: {after['usuarios']}")
        print(f"  funcionarios: {after['funcionarios']}")
        print(f"  logs_auditoria: {after['logs_auditoria']}")

    print('Migracao concluida com sucesso.')


if __name__ == '__main__':
    main()
