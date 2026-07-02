# tests/test_genomes.py
import pytest
import respx
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

FAKE_NCBI_RESPONSE = {
    "reports": [
        {
            "accession": "GCF_000005845.2",
            "organism": {
                "organism_name": "Escherichia coli str. K-12 substr. MG1655",
                "tax_id": 511145,
            },
            "assembly_info": {
                "assembly_level": "Complete Genome",
                "assembly_name": "ASM584v2",
                "submitter": "Univ. Wisconsin",
            },
        }
    ]
}


@respx.mock
def test_get_genome_by_accession_success():
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_000005845.2/dataset_report"
    respx.get(url).mock(return_value=httpx.Response(200, json=FAKE_NCBI_RESPONSE))

    response = client.get("/genomes/accession/GCF_000005845.2")

    assert response.status_code == 200
    data = response.json()
    assert data["accession"] == "GCF_000005845.2"
    assert data["organism_name"] == "Escherichia coli str. K-12 substr. MG1655"
    assert data["tax_id"] == 511145

@respx.mock
def test_get_genome_by_accession_not_found():
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_FAKE123/dataset_report"
    respx.get(url).mock(return_value=httpx.Response(404))

    response = client.get("/genomes/accession/GCF_FAKE123")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

@respx.mock
def test_get_genome_by_accession_rate_limited():
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_FAKE123/dataset_report"
    respx.get(url).mock(return_value=httpx.Response(429))

    response = client.get("/genomes/accession/GCF_FAKE123")

    assert response.status_code == 503
    assert "rate-limiting" in response.json()["detail"].lower()