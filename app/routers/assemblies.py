# app/routers/assemblies.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, not_
from typing import Optional

from app.database import get_db
from app.models import Assembly
from app.schemas import AssemblyListResponse, AssemblySummary
from app.routers.qc import PASSES, ENRICHED

router = APIRouter(tags=["assemblies"])


@router.get("/assemblies", response_model=AssemblyListResponse)
async def browse_assemblies(
    species_tax_id: Optional[int] = None,
    assembly_level: Optional[str] = None,
    submitter: Optional[str] = None,
    min_contigs: Optional[int] = None,
    max_contigs: Optional[int] = None,
    passes_qc: Optional[bool] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(Assembly)
    count_query = select(func.count(Assembly.accession))

    if species_tax_id is not None:
        query = query.where(Assembly.species_tax_id == species_tax_id)
        count_query = count_query.where(Assembly.species_tax_id == species_tax_id)

    if assembly_level is not None:
        query = query.where(Assembly.assembly_level == assembly_level)
        count_query = count_query.where(Assembly.assembly_level == assembly_level)

    if submitter is not None:
        query = query.where(Assembly.submitter.ilike(f"%{submitter}%"))
        count_query = count_query.where(Assembly.submitter.ilike(f"%{submitter}%"))

    if min_contigs is not None:
        query = query.where(Assembly.number_of_contigs >= min_contigs)
        count_query = count_query.where(Assembly.number_of_contigs >= min_contigs)

    if max_contigs is not None:
        query = query.where(Assembly.number_of_contigs <= max_contigs)
        count_query = count_query.where(Assembly.number_of_contigs <= max_contigs)

    if passes_qc is not None:
        # reuse the QC gate from the /qc router so thresholds stay single-sourced.
        # passes_qc=false means "enriched but failing", not "not yet enriched".
        qc_predicate = PASSES if passes_qc else and_(ENRICHED, not_(PASSES))
        query = query.where(qc_predicate)
        count_query = count_query.where(qc_predicate)

    total_count = await db.scalar(count_query)

    query = query.order_by(Assembly.accession).limit(limit).offset(offset)
    result = await db.execute(query)
    rows = result.scalars().all()

    return AssemblyListResponse(
        total_count=total_count,
        assemblies=[AssemblySummary.model_validate(row) for row in rows],
        next_page_token=None,
    )