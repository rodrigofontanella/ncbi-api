"""
Quality-control gate over enriched assemblies.

Surfaces which genomes are safe to feed into AMR surveillance / strain typing /
comparative genomics, based on the enrichment columns (CheckM completeness &
contamination, ANI best-match identity). Thresholds follow MIMAG "high quality"
(completeness >= 90, contamination < 5) plus an ANI species-boundary check
(best-match ANI >= 95), which flags mislabeled or ambiguous genomes.

Endpoints:
  GET /qc/summary                     counts of passing / failing / not-yet-enriched
  GET /qc/assemblies?status=passing   filterable, paginated list with per-row reasons
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Assembly
from app.schemas import AssemblySummary

router = APIRouter(prefix="/qc", tags=["qc"])

# --- thresholds (single source of truth) ------------------------------------
MIN_COMPLETENESS = 90.0
MAX_CONTAMINATION = 5.0
MIN_ANI = 95.0

# --- reusable SQL predicates ------------------------------------------------
ENRICHED = Assembly.checkm_completeness.is_not(None)
COMPLETE_OK = Assembly.checkm_completeness >= MIN_COMPLETENESS
# NULL contamination is common in NCBI and is not by itself a failure.
CONTAM_OK = func.coalesce(Assembly.checkm_contamination, 0) < MAX_CONTAMINATION
ANI_OK = Assembly.ani_best_match_percent >= MIN_ANI
PASSES = and_(ENRICHED, COMPLETE_OK, CONTAM_OK, ANI_OK)


class QCThresholds(BaseModel):
    min_completeness: float = MIN_COMPLETENESS
    max_contamination: float = MAX_CONTAMINATION
    min_ani: float = MIN_ANI


class QCSummary(BaseModel):
    total_assemblies: int
    enriched: int
    not_enriched: int
    passing: int
    failing: int
    failure_reasons: Dict[str, int]  # counts may overlap (a row can fail >1 check)
    thresholds: QCThresholds


class QCAssemblyEntry(AssemblySummary):
    passes_qc: bool
    qc_failures: List[str]


class QCAssemblyListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[QCAssemblyEntry]


def evaluate_qc(a: Assembly) -> tuple[bool, List[str]]:
    """Return (passes, [failure_reasons]) for one assembly row."""
    if a.checkm_completeness is None:
        return False, ["not_enriched"]
    failures: List[str] = []
    if float(a.checkm_completeness) < MIN_COMPLETENESS:
        failures.append("low_completeness")
    if a.checkm_contamination is not None and float(a.checkm_contamination) >= MAX_CONTAMINATION:
        failures.append("high_contamination")
    if a.ani_best_match_percent is None or float(a.ani_best_match_percent) < MIN_ANI:
        failures.append("low_ani")
    return (len(failures) == 0), failures


@router.get("/summary", response_model=QCSummary)
async def qc_summary(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count(Assembly.accession)))
    enriched = await db.scalar(select(func.count(Assembly.accession)).where(ENRICHED))
    passing = await db.scalar(select(func.count(Assembly.accession)).where(PASSES))

    low_completeness = await db.scalar(
        select(func.count(Assembly.accession)).where(
            and_(ENRICHED, Assembly.checkm_completeness < MIN_COMPLETENESS)
        )
    )
    high_contamination = await db.scalar(
        select(func.count(Assembly.accession)).where(
            Assembly.checkm_contamination >= MAX_CONTAMINATION
        )
    )
    low_ani = await db.scalar(
        select(func.count(Assembly.accession)).where(
            and_(
                ENRICHED,
                or_(Assembly.ani_best_match_percent.is_(None),
                    Assembly.ani_best_match_percent < MIN_ANI),
            )
        )
    )

    return QCSummary(
        total_assemblies=total,
        enriched=enriched,
        not_enriched=total - enriched,
        passing=passing,
        failing=enriched - passing,
        failure_reasons={
            "low_completeness": low_completeness,
            "high_contamination": high_contamination,
            "low_ani": low_ani,
        },
        thresholds=QCThresholds(),
    )


@router.get("/assemblies", response_model=QCAssemblyListResponse)
async def qc_assemblies(
    status: str = Query("passing", pattern="^(passing|failing|all)$"),
    organism: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List enriched assemblies filtered by QC status. `organism` is a
    case-insensitive prefix match (uses the ix_assemblies_organism_lower index).
    """
    filters = [ENRICHED]
    if organism:
        filters.append(func.lower(Assembly.organism_name).like(func.lower(organism) + "%"))
    if status == "passing":
        filters.append(PASSES)
    elif status == "failing":
        filters.append(not_(PASSES))

    where = and_(*filters)

    total = await db.scalar(select(func.count(Assembly.accession)).where(where))
    rows = (
        await db.execute(
            select(Assembly).where(where).order_by(Assembly.accession).limit(limit).offset(offset)
        )
    ).scalars().all()

    items: List[QCAssemblyEntry] = []
    for a in rows:
        ok, fails = evaluate_qc(a)
        base = AssemblySummary.model_validate(a).model_dump()
        items.append(QCAssemblyEntry(**base, passes_qc=ok, qc_failures=fails))

    return QCAssemblyListResponse(total=total or 0, limit=limit, offset=offset, items=items)