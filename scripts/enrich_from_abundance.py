"""
Resolve the species in a microbiome abundance table to NCBI RefSeq assemblies
and backfill the enrichment columns (contig_n50, checkm_completeness,
checkm_contamination, ani_best_match_organism, ani_best_match_percent) that the
bulk RefSeq catalog import leaves NULL.

For each species in the abundance CSV:
  1. normalize the name into candidate NCBI query strings;
  2. find assemblies already in the DB (matching by name) that still lack
     enrichment data, and/or resolve the species against NCBI if it isn't in the
     DB at all (inserting a base row);
  3. fetch each target assembly's dataset_report, parse the CheckM/ANI/N50
     fields with the app's existing parse_assembly_summary(), and UPDATE the row
     (filling NULLs only, unless --force).

A per-species audit CSV is written so you can see exactly what resolved.

Usage:
  python scripts/enrich_from_abundance.py abundance.csv
  python scripts/enrich_from_abundance.py abundance.csv --dry-run --limit 25
  python scripts/enrich_from_abundance.py abundance.csv --force --audit out.csv

Reads NCBI_API_KEY from settings; with a key you can safely lower --sleep.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import (
    AsyncSessionLocal,
    ENRICHMENT_COLUMNS,
    fill_enrichment,
    find_accessions_for_organism,
    upsert_assembly,
)
from app.ncbi_client import NCBINotFoundError, NCBIUnavailableError, ncbi_client
from app.resolver import normalize_name, resolve_organism
from app.schemas import parse_assembly_summary

AUDIT_FIELDS = [
    "species",
    "status",
    "resolved_query",
    "accession",
    *ENRICHMENT_COLUMNS,
]


def read_species(csv_path: str) -> list[str]:
    """Read the 'Taxonomy' column from the abundance CSV, preserving order."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "Taxonomy" not in reader.fieldnames:
            raise SystemExit(f"'Taxonomy' column not found. Columns: {reader.fieldnames[:5]}...")
        seen, out = set(), []
        for row in reader:
            name = (row["Taxonomy"] or "").strip()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


async def _fetch_report_with_retry(accession: str, retries: int, backoff: float) -> dict | None:
    """Fetch one assembly dataset_report, retrying on transient NCBI errors."""
    for attempt in range(retries + 1):
        try:
            return await ncbi_client.get_assembly_by_accession(accession)
        except NCBINotFoundError:
            return None
        except NCBIUnavailableError:
            if attempt == retries:
                raise
            await asyncio.sleep(backoff * (2 ** attempt))
    return None


def _enrichment_values(report: dict) -> dict:
    """Pull just the enrichment columns out of a parsed assembly summary."""
    summary = parse_assembly_summary(report)
    data = summary.model_dump()
    return {col: data.get(col) for col in ENRICHMENT_COLUMNS}


async def process_species(
    db, species: str, args, audit_writer
) -> str:
    """Handle one species end-to-end. Returns a short status string."""
    candidates = normalize_name(species)

    # 1) existing DB rows for this species that still lack enrichment
    accessions = await find_accessions_for_organism(db, candidates, only_missing=True)
    status = "db_hit"

    # 2) not in DB (missing) -> is it in the DB at all?
    if not accessions:
        present = await find_accessions_for_organism(db, candidates, only_missing=False)
        if present:
            audit_writer.writerow(
                {"species": species, "status": "already_enriched",
                 "resolved_query": candidates[0], "accession": present[0]}
            )
            return "already_enriched"

        # 3) resolve against NCBI and insert a base row
        if args.no_resolve:
            audit_writer.writerow({"species": species, "status": "not_in_db"})
            return "not_in_db"
        try:
            report = await resolve_organism(ncbi_client, species)
        except NCBIUnavailableError:
            await asyncio.sleep(args.backoff)
            report = await resolve_organism(ncbi_client, species)
        if report is None:
            audit_writer.writerow({"species": species, "status": "unresolved"})
            return "unresolved"

        summary = parse_assembly_summary(report)
        if not args.dry_run:
            await upsert_assembly(db, summary.model_dump(exclude={"cached_at"}))
        accessions = [summary.accession]
        status = "resolved"

    # cap enrichment fan-out per species (0 = unlimited)
    if args.max_per_species > 0:
        accessions = accessions[: args.max_per_species]

    filled_any = False
    for accession in accessions:
        report = await _fetch_report_with_retry(accession, args.retries, args.backoff)
        await asyncio.sleep(args.sleep)
        if report is None:
            audit_writer.writerow(
                {"species": species, "status": "report_missing",
                 "resolved_query": candidates[0], "accession": accession}
            )
            continue

        values = _enrichment_values(report)
        if not args.dry_run:
            await fill_enrichment(db, accession, values, force=args.force)
        filled_any = filled_any or any(v is not None for v in values.values())

        audit_writer.writerow(
            {"species": species, "status": status,
             "resolved_query": report.get("_resolved_query", candidates[0]),
             "accession": accession, **values}
        )

    return status if filled_any else f"{status}_no_data"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve + enrich abundance-table species from NCBI.")
    parser.add_argument("csv_path", help="Path to abundance.csv (needs a 'Taxonomy' column)")
    parser.add_argument("--audit", default="enrichment_audit.csv", help="Audit CSV output path")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N species (0 = all)")
    parser.add_argument("--max-per-species", type=int, default=5,
                        help="Max assemblies to enrich per species (0 = unlimited)")
    parser.add_argument("--sleep", type=float, default=0.34,
                        help="Seconds between NCBI calls (use ~0.11 with an API key)")
    parser.add_argument("--retries", type=int, default=3, help="Retries on transient NCBI errors")
    parser.add_argument("--backoff", type=float, default=1.0, help="Base backoff seconds")
    parser.add_argument("--force", action="store_true", help="Overwrite existing values (default: fill NULLs only)")
    parser.add_argument("--no-resolve", action="store_true", help="Only enrich rows already in the DB; skip NCBI taxon resolution")
    parser.add_argument("--dry-run", action="store_true", help="Resolve + report but write nothing to the DB")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Species processed in parallel. Keep concurrency/sleep within NCBI limits: "
                             "~3 req/s without an API key, ~10 req/s with one.")
    args = parser.parse_args()

    species = read_species(args.csv_path)
    if args.limit > 0:
        species = species[: args.limit]

    print(f"Processing {len(species)} species "
          f"({'DRY RUN' if args.dry_run else 'writing to DB'}), "
          f"concurrency={args.concurrency}; audit -> {args.audit}")

    counts: dict[str, int] = {}
    done = 0
    total = len(species)
    sem = asyncio.Semaphore(max(1, args.concurrency))
    audit_path = Path(args.audit)

    with audit_path.open("w", newline="", encoding="utf-8") as af:
        writer = csv.DictWriter(af, fieldnames=AUDIT_FIELDS)
        writer.writeheader()

        async def worker(sp: str) -> None:
            nonlocal done
            # Each task gets its own session: an AsyncSession must not be shared
            # across concurrent tasks.
            async with sem:
                try:
                    async with AsyncSessionLocal() as db:
                        status = await process_species(db, sp, args, writer)
                        if not args.dry_run:
                            await db.commit()
                except NCBIUnavailableError as e:
                    status = "ncbi_unavailable"
                    print(f"  ! {sp}: {e}")
                except Exception as e:  # noqa: BLE001 - keep the batch alive, record the failure
                    status = "error"
                    print(f"  ! {sp}: {type(e).__name__}: {e}")
            counts[status] = counts.get(status, 0) + 1
            done += 1
            if done % 25 == 0 or done == total:
                print(f"  [{done}/{total}] last: {sp} -> {status}")

        await asyncio.gather(*(worker(sp) for sp in species))

    print("\nSummary:")
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status:20s} {n}")
    print(f"\nAudit written to {audit_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())