# app/schemas.py
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import date, datetime


class AssemblySummary(BaseModel):
    accession: str
    organism_name: str
    tax_id: Optional[int] = None
    species_tax_id: Optional[int] = None
    assembly_level: Optional[str] = None
    assembly_name: Optional[str] = None
    submitter: Optional[str] = None
    bioproject_accession: Optional[str] = None
    biosample_accession: Optional[str] = None
    contig_n50: Optional[int] = None
    total_sequence_length: Optional[int] = None
    number_of_contigs: Optional[int] = None
    gc_percent: Optional[float] = None
    submission_date: Optional[date] = None
    checkm_completeness: Optional[float] = None
    checkm_contamination: Optional[float] = None
    ani_best_match_organism: Optional[str] = None
    ani_best_match_percent: Optional[float] = None
    cached_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AssemblyListResponse(BaseModel):
    total_count: int
    assemblies: List[AssemblySummary]
    next_page_token: Optional[str] = None


class TopSpeciesEntry(BaseModel):
    species_tax_id: int
    example_organism_name: str
    assembly_count: int


class AssemblyQualityStats(BaseModel):
    avg_contig_count: Optional[float] = None
    median_contig_count: Optional[float] = None
    contig_count_distribution: Dict[str, int]
    avg_gc_percent: Optional[float] = None


class OverviewStats(BaseModel):
    total_assemblies: int
    distinct_tax_ids: int
    with_checkm_data: int
    assembly_level_breakdown: Dict[str, int]


def parse_assembly_summary(raw: dict) -> "AssemblySummary":
    org = raw.get("organism", {})
    assembly_info = raw.get("assembly_info", {})
    assembly_stats = raw.get("assembly_stats", {})
    biosample = assembly_info.get("biosample", {})
    checkm = raw.get("checkm_info", {})
    ani = raw.get("average_nucleotide_identity", {})
    ani_best_match = ani.get("best_ani_match", {})

    total_length = assembly_stats.get("total_sequence_length")

    return AssemblySummary(
        accession=raw.get("accession", "unknown"),
        organism_name=org.get("organism_name", "unknown"),
        tax_id=org.get("tax_id"),
        assembly_level=assembly_info.get("assembly_level"),
        assembly_name=assembly_info.get("assembly_name"),
        submitter=assembly_info.get("submitter"),
        bioproject_accession=assembly_info.get("bioproject_accession"),
        biosample_accession=biosample.get("accession"),
        contig_n50=assembly_stats.get("contig_n50"),
        total_sequence_length=int(total_length) if total_length else None,
        number_of_contigs=assembly_stats.get("number_of_contigs"),
        gc_percent=assembly_stats.get("gc_percent"),
        submission_date=assembly_info.get("release_date"),
        checkm_completeness=checkm.get("completeness"),
        checkm_contamination=checkm.get("contamination"),
        ani_best_match_organism=ani_best_match.get("organism_name"),
        ani_best_match_percent=ani_best_match.get("ani"),
    )