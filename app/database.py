from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models import Assembly

engine = create_async_engine(settings.database_url, echo=False)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def upsert_assembly(db: AsyncSession, data: dict) -> None:
    stmt = pg_insert(Assembly).values(**data)
    stmt = stmt.on_conflict_do_nothing(index_elements=["accession"])
    await db.execute(stmt)