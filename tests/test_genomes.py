from sqlalchemy import select
from app.models import Assembly

import pytest
import respx
import httpx
from app.config import settings

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


@pytest.mark.asyncio
@respx.mock
async def test_get_genome_by_accession_success(client):
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_000005845.2/dataset_report"
    respx.get(url).mock(return_value=httpx.Response(200, json=FAKE_NCBI_RESPONSE))

    response = await client.get("/genomes/accession/GCF_000005845.2")

    assert response.status_code == 200
    data = response.json()
    assert data["accession"] == "GCF_000005845.2"
    assert data["organism_name"] == "Escherichia coli str. K-12 substr. MG1655"
    assert data["tax_id"] == 511145


@pytest.mark.asyncio
@respx.mock
async def test_get_genome_by_accession_not_found(client):
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_FAKE123/dataset_report"
    respx.get(url).mock(return_value=httpx.Response(404))

    response = await client.get("/genomes/accession/GCF_FAKE123")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_get_genome_by_accession_rate_limited(client):
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_FAKE123/dataset_report"
    respx.get(url).mock(return_value=httpx.Response(429))

    response = await client.get("/genomes/accession/GCF_FAKE123")

    assert response.status_code == 503
    assert "rate" in response.json()["detail"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_accession_cache_miss_inserts_row(client, db_session):
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_000005845.2/dataset_report"
    respx.get(url).mock(return_value=httpx.Response(200, json=FAKE_NCBI_RESPONSE))

    response = await client.get("/genomes/accession/GCF_000005845.2")
    assert response.status_code == 200

    result = await db_session.execute(
        select(Assembly).where(Assembly.accession == "GCF_000005845.2")
    )
    row = result.scalar_one_or_none()

    assert row is not None
    assert row.organism_name == "Escherichia coli str. K-12 substr. MG1655"
    assert row.cached_at is not None



@pytest.mark.asyncio
@respx.mock
async def test_accession_cache_hit_skips_ncbi(client, db_session):
    url = f"{settings.ncbi_base_url}/genome/accession/GCF_000005845.2/dataset_report"
    route = respx.get(url).mock(return_value=httpx.Response(200, json=FAKE_NCBI_RESPONSE))

    # First call — cache miss, should call NCBI
    await client.get("/genomes/accession/GCF_000005845.2")
    assert route.call_count == 1

    # Second call — should be a cache hit, NCBI should NOT be called again
    response = await client.get("/genomes/accession/GCF_000005845.2")
    assert response.status_code == 200
    assert route.call_count == 1  # still 1, not 2