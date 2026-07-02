from pydantic import BaseModel
from typing import Optional, List


class AssemblySummary(BaseModel):
    accession: str
    organism_name: str
    tax_id: Optional[int] = None
    assembly_level: Optional[str] = None
    assembly_name: Optional[str] = None
    submitter: Optional[str] = None


class AssemblyListResponse(BaseModel):
    total_count: int
    assemblies: List[AssemblySummary]
    next_page_token: Optional[str] = None


def parse_assembly_summary(raw: dict) -> "AssemblySummary":
    org = raw.get("organism", {})
    assembly_info = raw.get("assembly_info", {})
    return AssemblySummary(
        accession=raw.get("accession", "unknown"),
        organism_name=org.get("organism_name", "unknown"),
        tax_id=org.get("tax_id"),
        assembly_level=assembly_info.get("assembly_level"),
        assembly_name=assembly_info.get("assembly_name"),
        submitter=assembly_info.get("submitter"),
    )