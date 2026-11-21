import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://agro_admin:DevPassword2026!@db:5432/agro_berries_erp")
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
