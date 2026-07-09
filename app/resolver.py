# app/resolver.py
"""
Resolve free-text taxonomy names (e.g. from a microbiome abundance table) to
NCBI RefSeq assemblies, and choose the best assembly per organism.

The abundance table gives species names that are:
  * lowercase                      -> "acetivibrio ethanolgignens"
  * bracketed / provisional genus  -> "[ruminococcus] gnavus"
  * strain-level "sp." names       -> "acidovorax sp. 1608163"

NCBI's taxon lookup is fairly tolerant, but to maximise the hit-rate we generate
an ordered list of candidate query strings per name and try them in order until
one resolves. This module contains only pure logic + thin calls into the
existing NCBIClient, so it is easy to unit-test.
"""
from __future__ import annotations

import re
from typing import Optional

# Assembly-level preference (lower rank == better).
_LEVEL_RANK = {
    "Complete Genome": 0,
    "Chromosome": 1,
    "Scaffold": 2,
    "Contig": 3,
}

# RefSeq category preference (lower rank == better).
_REFSEQ_CATEGORY_RANK = {
    "reference genome": 0,
    "representative genome": 1,
}


def _title_genus(token: str) -> str:
    """Capitalise the first letter of the genus token, leave the rest intact."""
    return token[:1].upper() + token[1:] if token else token


def normalize_name(raw: str) -> list[str]:
    """
    Turn one raw taxonomy string into an ordered list of candidate query strings
    to try against NCBI, most-specific first.

    Examples
    --------
    "acetivibrio ethanolgignens" -> ["Acetivibrio ethanolgignens"]
    "[ruminococcus] gnavus"      -> ["[Ruminococcus] gnavus", "Ruminococcus gnavus"]
    "acidovorax sp. 1608163"     -> ["Acidovorax sp. 1608163", "Acidovorax"]
    """
    name = raw.strip()
    candidates: list[str] = []

    bracket = re.match(r"^\[([A-Za-z]+)\]\s+(.*)$", name)
    if bracket:
        genus = _title_genus(bracket.group(1))
        rest = bracket.group(2).strip()
        candidates.append(f"[{genus}] {rest}")  # NCBI provisional scientific name
        candidates.append(f"{genus} {rest}")    # de-bracketed fallback
    else:
        parts = name.split()
        if parts:
            parts[0] = _title_genus(parts[0])
        candidates.append(" ".join(parts))

    # "Genus sp. <strain>" -> add genus-level fallback.
    sp_match = re.match(r"^\[?([A-Za-z]+)\]?\s+sp\.", candidates[0])
    if sp_match:
        genus = _title_genus(sp_match.group(1))
        candidates.append(genus)

    # de-duplicate, preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _assembly_sort_key(report: dict) -> tuple:
    """
    Build a sort key so that the *best* assembly sorts first.
    Priority: RefSeq (GCF_) > refseq_category > assembly_level > higher N50.
    """
    accession = report.get("accession", "") or ""
    info = report.get("assembly_info", {}) or {}
    stats = report.get("assembly_stats", {}) or {}

    is_refseq = 0 if accession.startswith("GCF_") else 1

    category = (info.get("refseq_category") or "").lower()
    category_rank = _REFSEQ_CATEGORY_RANK.get(category, 2)

    level_rank = _LEVEL_RANK.get(info.get("assembly_level"), 4)

    # higher N50 is better -> negate for ascending sort
    try:
        n50 = int(stats.get("contig_n50") or 0)
    except (TypeError, ValueError):
        n50 = 0

    return (is_refseq, category_rank, level_rank, -n50)


def pick_best_assembly(reports: list[dict]) -> Optional[dict]:
    """Choose the single best assembly report from a taxon dataset_report."""
    if not reports:
        return None
    return sorted(reports, key=_assembly_sort_key)[0]


async def resolve_organism(ncbi_client, raw_name: str, page_size: int = 50) -> Optional[dict]:
    """
    Resolve a raw taxonomy name to the best RefSeq assembly report.

    Tries each normalized candidate in order; returns the first that resolves.
    Returns the raw NCBI report dict (feed it to parse_assembly_summary), or None.

    Import errors are deliberately not caught here except NCBINotFoundError so
    transient NCBI failures propagate to the caller's retry logic.
    """
    from app.ncbi_client import NCBINotFoundError

    for candidate in normalize_name(raw_name):
        try:
            data = await ncbi_client.get_assemblies_by_organism(candidate, page_size=page_size)
        except NCBINotFoundError:
            continue
        best = pick_best_assembly(data.get("reports", []))
        if best is not None:
            best["_resolved_query"] = candidate  # breadcrumb for the audit trail
            return best
    return None
