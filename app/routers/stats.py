# app/routers/stats.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from typing import List
from app.database import get_db
from app.models import Assembly
from app.schemas import OverviewStats, TopSpeciesEntry, AssemblyQualityStats


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


@router.get("/top-species", response_model=List[TopSpeciesEntry])
async def get_top_species(limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Assembly.species_tax_id,
            func.max(Assembly.organism_name).label("example_organism_name"),
            func.count(Assembly.accession).label("assembly_count"),
        )
        .where(Assembly.species_tax_id.is_not(None))
        .group_by(Assembly.species_tax_id)
        .order_by(func.count(Assembly.accession).desc())
        .limit(limit)
    )

    return [
        TopSpeciesEntry(
            species_tax_id=row.species_tax_id,
            example_organism_name=row.example_organism_name,
            assembly_count=row.assembly_count,
        )
        for row in result.all()
    ]



@router.get("/assembly-quality", response_model=AssemblyQualityStats)
async def get_assembly_quality_stats(db: AsyncSession = Depends(get_db)):
    avg_contigs = await db.scalar(select(func.avg(Assembly.number_of_contigs)))

    median_contigs = await db.scalar(
        select(func.percentile_cont(0.5).within_group(Assembly.number_of_contigs))
    )

    bucket_expr = case(
        (Assembly.number_of_contigs == 1, "1 (complete)"),
        (Assembly.number_of_contigs.between(2, 10), "2-10"),
        (Assembly.number_of_contigs.between(11, 100), "11-100"),
        (Assembly.number_of_contigs > 100, "101+"),
        else_="unknown",
    )

    bucket_result = await db.execute(
        select(bucket_expr.label("bucket"), func.count(Assembly.accession))
        .group_by(bucket_expr)
    )
    contig_distribution = {bucket: count for bucket, count in bucket_result.all()}

    avg_gc = await db.scalar(select(func.avg(Assembly.gc_percent)))

    return AssemblyQualityStats(
        avg_contig_count=round(avg_contigs, 1) if avg_contigs else None,
        median_contig_count=median_contigs,
        contig_count_distribution=contig_distribution,
        avg_gc_percent=round(float(avg_gc), 2) if avg_gc else None,
    )

