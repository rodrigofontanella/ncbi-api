from fastapi import APIRouter, HTTPException
from typing import Optional
from app.ncbi_client import ncbi_client, NCBINotFoundError, NCBIUnavailableError
from app.schemas import AssemblySummary, AssemblyListResponse, parse_assembly_summary

router = APIRouter(prefix="/genomes", tags=["genomes"])

@router.get("/accession/{accession}", response_model=AssemblySummary)
async def get_genome_by_accession(accession: str):
    try:
        raw = await ncbi_client.get_assembly_by_accession(accession)
    except NCBINotFoundError:
        raise HTTPException(status_code=404, detail=f"Assembly '{accession}' not found")
    except NCBIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return parse_assembly_summary(raw)


@router.get("/taxid/{taxid}", response_model=AssemblyListResponse)
async def get_genomes_by_taxid(
    taxid: int, page_size: int = 20, page_token: Optional[str] = None
):
    try:
        data = await ncbi_client.get_assemblies_by_taxid(taxid, page_size, page_token)
    except NCBINotFoundError:
        raise HTTPException(status_code=404, detail=f"No assemblies found for taxid {taxid}")
    except NCBIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    assemblies = [parse_assembly_summary(raw) for raw in data["reports"]]
    return AssemblyListResponse(
        total_count=data.get("total_count", len(assemblies)),
        assemblies=assemblies,
        next_page_token=data.get("next_page_token"),
    )


@router.get("/organism/{organism_name}", response_model=AssemblyListResponse)
async def get_genomes_by_organism(
    organism_name: str, page_size: int = 20, page_token: Optional[str] = None
):
    try:
        data = await ncbi_client.get_assemblies_by_organism(organism_name, page_size, page_token)
    except NCBINotFoundError:
        raise HTTPException(status_code=404, detail=f"No assemblies found for organism '{organism_name}'")
    except NCBIUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    assemblies = [parse_assembly_summary(raw) for raw in data["reports"]]
    return AssemblyListResponse(
        total_count=data.get("total_count", len(assemblies)),
        assemblies=assemblies,
        next_page_token=data.get("next_page_token"),
    )