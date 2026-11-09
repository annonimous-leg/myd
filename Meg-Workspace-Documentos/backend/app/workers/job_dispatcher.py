"""Independent supervised database-to-broker publisher."""
import asyncio
import logging
from app.core.process_queue import publicar_pendientes
from app.models.base import engine


async def main():
    try:
        while True:
            try:
                await publicar_pendientes()
            except Exception:
                logging.getLogger(__name__).exception('process_dispatcher_unavailable')
            await asyncio.sleep(2)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
