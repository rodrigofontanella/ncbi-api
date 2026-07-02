import httpx
from app.config import settings
from typing import Optional

class NCBINotFoundError(Exception):
    pass

class NCBIClient:
    def __init__(self):
        self.base_url = settings.ncbi_base_url
        self.headers = {"api-key": settings.ncbi_api_key} if settings.ncbi_api_key else {}

    async def get_assembly_by_accession(self, accession: str) -> dict:
        url = f"{self.base_url}/genome/accession/{accession}/dataset_report"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self.headers)

        if response.status_code == 404:
            raise NCBINotFoundError(f"No assembly found for accession {accession}")
        response.raise_for_status()

        data = response.json()
        reports = data.get("reports", [])
        if not reports:
            raise NCBINotFoundError(f"No assembly found for accession {accession}")
        return reports[0]
    
    async def get_assemblies_by_taxid(
        self, taxid: int, page_size: int = 20, page_token: Optional[str] = None
    ) -> dict:
        url = f"{self.base_url}/genome/taxon/{taxid}/dataset_report"
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self.headers, params=params)

        if response.status_code == 404:
            raise NCBINotFoundError(f"No assemblies found for taxid {taxid}")
        response.raise_for_status()

        data = response.json()
        if not data.get("reports"):
            raise NCBINotFoundError(f"No assemblies found for taxid {taxid}")
        return data
    
    async def get_assemblies_by_organism(
        self, organism_name: str, page_size: int = 20, page_token: Optional[str] = None
    ) -> dict:
        url = f"{self.base_url}/genome/taxon/{organism_name}/dataset_report"
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=self.headers, params=params)

        if response.status_code == 404:
            raise NCBINotFoundError(f"No assemblies found for organism '{organism_name}'")
        response.raise_for_status()

        data = response.json()
        if not data.get("reports"):
            raise NCBINotFoundError(f"No assemblies found for organism '{organism_name}'")
        return data

ncbi_client = NCBIClient()