# app/routers/genomes.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.database import get_db, upsert_assembly
from app.models import Assembly
from app.ncbi_client import ncbi_client, NCBINotFoundError, NCBIUnavailableError
from app.schemas import AssemblySummary, AssemblyListResponse, parse_assembly_summary

router = APIRouter(prefix="/genomes", tags=["genomes"])
CACHE_TTL = timedelta(days=30)

@router.get("/accession/{accession}", response_model=AssemblySummary)
async def get_genome_by_accession(accession: str, db: AsyncSession = Depends(get_db)):
    # 1. Check the cache first
    result = await db.execute(select(Assembly).where(Assembly.accession == accession))
    cached = result.scalar_one_or_none()

    if cached is not None:
        age = datetime.now(timezone.utc) - cached.cached_at
        if age < CACHE_TTL:
            return AssemblySummary.model_validate(cached)
        # else: fall through — treat as stale, refetch and update in place

     # 2. Cache miss (or stale) — go to NCBI
    try:
        raw = await ncbi_client.get_assembly_by_accession(accession)
    except NCBINotFoundError:
        raise HTTPException(status_code=404, detail=f"Assembly '{accession}' not found")
    except NCBIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    summary = parse_assembly_summary(raw)
    fields = summary.model_dump(exclude={"cached_at"})

    if cached is not None:
        # Row exists but was stale — update it in place
        for key, value in fields.items():
            setattr(cached, key, value)
        cached.cached_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(cached)
        return AssemblySummary.model_validate(cached)

    # 3. Truly new — insert a fresh row
    db_row = Assembly(**fields)
    db.add(db_row)
    await db.commit()
    await db.refresh(db_row)
    return AssemblySummary.model_validate(db_row)


@router.get("/taxid/{taxid}", response_model=AssemblyListResponse)
async def get_genomes_by_taxid(
    taxid: int, page_size: int = 20, page_token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await ncbi_client.get_assemblies_by_taxid(taxid, page_size, page_token)
    except NCBINotFoundError:
        raise HTTPException(status_code=404, detail=f"No assemblies found for taxid {taxid}")
    except NCBIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    assemblies = [parse_assembly_summary(raw) for raw in data["reports"]]

    for summary in assemblies:
        await upsert_assembly(db, summary.model_dump(exclude={"cached_at"}))
    await db.commit()

    return AssemblyListResponse(
        total_count=data.get("total_count", len(assemblies)),
        assemblies=assemblies,
        next_page_token=data.get("next_page_token"),
    )



@router.get("/organism/{organism_name}", response_model=AssemblyListResponse)
async def get_genomes_by_organism(
    organism_name: str, page_size: int = 20, page_token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        data = await ncbi_client.get_assemblies_by_organism(organism_name, page_size, page_token)
    except NCBINotFoundError:
        raise HTTPException(status_code=404, detail=f"No assemblies found for organism {organism_name}")
    except NCBIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    assemblies = [parse_assembly_summary(raw) for raw in data["reports"]]

    for summary in assemblies:
        await upsert_assembly(db, summary.model_dump(exclude={"cached_at"}))
    await db.commit()

    return AssemblyListResponse(
        total_count=data.get("total_count", len(assemblies)),
        assemblies=assemblies,
        next_page_token=data.get("next_page_token"),
    )

