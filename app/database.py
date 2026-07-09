from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, update, or_, func
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



# Columns filled by the abundance-enrichment pass.
ENRICHMENT_COLUMNS = (
    "contig_n50",
    "checkm_completeness",
    "checkm_contamination",
    "ani_best_match_organism",
    "ani_best_match_percent",
)


async def find_accessions_for_organism(
    db: AsyncSession, candidates: list[str], only_missing: bool = True
) -> list[str]:
    """
    Return accessions already in the DB whose organism_name matches any of the
    candidate name forms (prefix match, case-insensitive). When only_missing is
    True, restrict to rows that still lack enrichment data (any of the enrichment
    columns is NULL) so we don't re-fetch rows we've already filled.
    """
    if not candidates:
        return []

    name_filters = [
        func.lower(Assembly.organism_name).like(func.lower(c) + "%")
        for c in candidates
    ]
    query = select(Assembly.accession).where(or_(*name_filters))

    if only_missing:
        missing = or_(*(getattr(Assembly, col).is_(None) for col in ENRICHMENT_COLUMNS))
        query = query.where(missing)

    result = await db.execute(query)
    return [row[0] for row in result.all()]


async def fill_enrichment(
    db: AsyncSession, accession: str, values: dict, force: bool = False
) -> int:
    """
    Fill enrichment columns for one accession.

    By default only NULL columns are populated (COALESCE(existing, new)) so we
    never clobber data that's already there. With force=True the fetched values
    overwrite whatever is present. Returns the number of rows updated.
    """
    payload = {k: values.get(k) for k in ENRICHMENT_COLUMNS if values.get(k) is not None}
    if not payload:
        return 0

    if force:
        set_values = payload
    else:
        set_values = {k: func.coalesce(getattr(Assembly, k), v) for k, v in payload.items()}

    stmt = update(Assembly).where(Assembly.accession == accession).values(**set_values)
    result = await db.execute(stmt)
    return result.rowcount or 0