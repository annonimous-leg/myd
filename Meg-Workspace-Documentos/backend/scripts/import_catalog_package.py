"""Import a private source package into an explicit existing user's tenant.

Example: python -m scripts.import_catalog_package --package /private/package
  --originals /private/pdfs --user-id UUID --source cmic_educativa_2026
No migrations, fictitious users or supplied SQL are executed by this command.
"""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.models.base import AsyncSessionLocal, engine
from app.models.user import User
from app.services.catalogo_importacion import import_package


async def main(args):
    try:
        async with AsyncSessionLocal() as db:
            user = await db.scalar(select(User).where(User.id == args.user_id))
            if user is None: raise ValueError('El usuario debe existir; no se crea una identidad ficticia')
            batch, created = await import_package(db, user, args.package, args.originals, set(args.source))
            print(json.dumps({'importacion_id': str(batch.id), 'creada': created, 'resumen': batch.resumen}, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--originals', type=Path, required=True)
    parser.add_argument('--user-id', type=UUID, required=True)
    parser.add_argument('--source', action='append', required=True, help='Explicit source identity; repeat for several sources')
    asyncio.run(main(parser.parse_args()))
