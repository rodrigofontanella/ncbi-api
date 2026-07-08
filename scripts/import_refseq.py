import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.database import engine
from app.models import Assembly

BATCH_SIZE = 2000


def na_to_none(value: str):
    return None if value == "na" or value == "" else value


def parse_row(row: dict) -> dict:
    genome_size = na_to_none(row["genome_size"])
    gc_percent = na_to_none(row["gc_percent"])
    contig_count = na_to_none(row["contig_count"])
    release_date_str = na_to_none(row["seq_rel_date"])

    return {
        "accession": row["assembly_accession"],
        "organism_name": row["organism_name"],
        "tax_id": int(row["taxid"]) if na_to_none(row["taxid"]) else None,
        "species_tax_id": int(row["species_taxid"]) if na_to_none(row["species_taxid"]) else None,
        "assembly_level": na_to_none(row["assembly_level"]),
        "assembly_name": na_to_none(row["asm_name"]),
        "submitter": na_to_none(row["asm_submitter"]),
        "bioproject_accession": na_to_none(row["bioproject"]),
        "biosample_accession": na_to_none(row["biosample"]),
        "total_sequence_length": int(genome_size) if genome_size else None,
        "number_of_contigs": int(contig_count) if contig_count else None,
        "gc_percent": float(gc_percent) if gc_percent else None,
        "submission_date": datetime.strptime(release_date_str, "%Y-%m-%d").date() if release_date_str else None,
    }


async def import_file(filepath: str):
    inserted = 0
    skipped = 0
    batch = []

    with open(filepath, newline="", encoding="utf-8") as f:
        lines = (line for line in f if not line.startswith("##"))
        first_line = next(lines).lstrip("#").strip()
        fieldnames = first_line.split("\t")

        reader = csv.DictReader(lines, fieldnames=fieldnames, delimiter="\t", quoting=csv.QUOTE_NONE)

        async with engine.begin() as conn:
            for row in reader:
                try:
                    batch.append(parse_row(row))
                except (ValueError, KeyError) as e:
                    skipped += 1
                    print(f"Skipped malformed row (accession: {row.get('assembly_accession', '?')}): {e}")
                    continue

                if len(batch) >= BATCH_SIZE:
                    stmt = pg_insert(Assembly).values(batch)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["accession"])
                    await conn.execute(stmt)
                    inserted += len(batch)
                    print(f"Processed {inserted} rows...")
                    batch = []

            if batch:
                stmt = pg_insert(Assembly).values(batch)
                stmt = stmt.on_conflict_do_nothing(index_elements=["accession"])
                await conn.execute(stmt)
                inserted += len(batch)

    print(f"Done. Total rows inserted: {inserted}, skipped: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_refseq.py <path_to_assembly_summary.txt>")
        sys.exit(1)
    asyncio.run(import_file(sys.argv[1]))