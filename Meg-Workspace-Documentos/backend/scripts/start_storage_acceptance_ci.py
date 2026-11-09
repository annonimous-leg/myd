"""Start the real, pinned Supabase Storage server in disposable GitHub staging.

No cloud account, mocked storage, public bucket or production data is used.
The reverse proxy only supplies Supabase's /storage/v1 routing prefix.
Configuration: https://github.com/supabase/storage/tree/v1.74.0
"""
import asyncio
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

import asyncpg
import httpx
import jwt
from sqlalchemy.engine import make_url


async def main():
    url = make_url(os.environ['DATABASE_URL'])
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('ENVIRONMENT') != 'staging'
            or url.database != 'bim_acceptance' or url.host not in ('localhost', '127.0.0.1')):
        raise SystemExit('Storage acceptance requires disposable local CI staging.')
    storage_url = url.set(drivername='postgresql', database='licitacion_storage')
    conn = await asyncpg.connect(url.set(drivername='postgresql').render_as_string(hide_password=False))
    try:
        # Storage's initial migration grants privileges to the historical
        # postgres role, even when DB_SUPER_USER names a different CI owner.
        # The PostGIS image only creates POSTGRES_USER (megalodon here).
        if not await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='postgres')"):
            await conn.execute('CREATE ROLE postgres NOLOGIN')
        await conn.execute('CREATE DATABASE licitacion_storage')
    finally:
        await conn.close()
    secret = secrets.token_urlsafe(48)
    key = jwt.encode({'role': 'service_role', 'iat': int(time.time()), 'exp': int(time.time()) + 7200}, secret, algorithm='HS256')
    # Only synthetic keys generated for this job. Never emit a reusable credential.
    print(f'::add-mask::{secret}')
    print(f'::add-mask::{key}')
    env = {
        'AUTH_JWT_SECRET': secret, 'AUTH_JWT_ALGORITHM': 'HS256', 'SERVICE_KEY': key,
        'DATABASE_URL': storage_url.render_as_string(hide_password=False),
        # Storage changes this owner's search_path at the cluster-role level.
        # Keep it separate from the app/migration login even in disposable CI.
        'DB_INSTALL_ROLES': 'true', 'DB_SUPER_USER': 'supabase_storage_admin',
        'STORAGE_BACKEND': 'file', 'STORAGE_FILE_BACKEND_PATH': '/var/lib/storage',
        'STORAGE_S3_BUCKET': 'ci-documents', 'IMAGE_TRANSFORMATION_ENABLED': 'false',
        'SERVER_PORT': '5000', 'SERVER_HOST': '127.0.0.1', 'TENANT_ID': 'licitacion-ci',
        'UPLOAD_FILE_SIZE_LIMIT': '52428800', 'UPLOAD_FILE_SIZE_LIMIT_STANDARD': '52428800',
    }
    command = ['docker', 'run', '-d', '--name', 'meg-storage-ci', '--network', 'host']
    for name in env:
        command.extend(['-e', name])
    subprocess.run([*command, 'supabase/storage-api:v1.74.0'], env={**os.environ, **env}, check=True, timeout=180)
    async with httpx.AsyncClient(timeout=5) as client:
        for attempt in range(120):
            try:
                response = await client.get('http://127.0.0.1:5000/status')
                if response.is_success:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError('The real Supabase Storage server did not become ready; inspect container logs.')
        response = await client.post('http://127.0.0.1:5000/bucket', headers={'Authorization': f'Bearer {key}'},
                                     json={'id': 'documentos', 'name': 'documentos', 'public': False})
        response.raise_for_status()
    with tempfile.TemporaryDirectory(prefix='meg-storage-proxy-') as directory:
        config = Path(directory) / 'default.conf'
        config.write_text('server { listen 127.0.0.1:5001; client_max_body_size 50m; '
                          'location /storage/v1/ { proxy_pass http://127.0.0.1:5000/; } }')
        subprocess.run(['docker', 'run', '-d', '--name', 'meg-storage-proxy-ci', '--network', 'host',
                        '-v', f'{config}:/etc/nginx/conf.d/default.conf:ro', 'nginx:1.28.0-alpine'],
                       check=True, timeout=180)
        # nginx reads the bind-mounted configuration on startup.
        async with httpx.AsyncClient(timeout=5) as client:
            for attempt in range(30):
                try:
                    if (await client.get('http://127.0.0.1:5001/storage/v1/status')).is_success:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
            else:
                raise RuntimeError('Storage proxy did not become ready.')
    # A ready storage server must not change the application's schema visibility.
    # Use a fresh process/connection, as the browser API will at startup.
    subprocess.run([sys.executable, '-m', 'scripts.verify_migrated_schema'],
                   check=True, timeout=60)
    with Path(os.environ['GITHUB_ENV']).open('a') as output:
        output.write(f'SUPABASE_URL=http://127.0.0.1:5001\nSUPABASE_SERVICE_KEY={key}\n')
    print('Real Supabase Storage v1.74.0 ready with a private acceptance bucket.')


if __name__ == '__main__':
    asyncio.run(main())
