"""Worker connections are never pooled across asyncio.run loops or prefork tasks.

The API retains its request pool. This is connection infrastructure only: each
worker domain owns its claims, transactions, expiry policy and recovery.
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.config import settings

worker_engine = create_async_engine(settings.database_async_url, poolclass=NullPool)
AsyncSessionLocal = async_sessionmaker(worker_engine, expire_on_commit=False, autoflush=False)
