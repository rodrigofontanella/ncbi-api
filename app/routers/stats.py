# app/routers/stats.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import Assembly
from app.schemas import OverviewStats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats(db: AsyncSession = Depends(get_db)):
    total_assemblies = await db.scalar(select(func.count(Assembly.accession)))

    distinct_tax_ids = await db.scalar(
        select(func.count(func.distinct(Assembly.tax_id)))
    )

    with_checkm_data = await db.scalar(
        select(func.count(Assembly.accession)).where(Assembly.checkm_completeness.is_not(None))
    )

    level_result = await db.execute(
        select(Assembly.assembly_level, func.count(Assembly.accession))
        .group_by(Assembly.assembly_level)
    )
    assembly_level_breakdown = {level or "unknown": count for level, count in level_result.all()}

    return OverviewStats(
        total_assemblies=total_assemblies,
        distinct_tax_ids=distinct_tax_ids,
        with_checkm_data=with_checkm_data,
        assembly_level_breakdown=assembly_level_breakdown,
    )