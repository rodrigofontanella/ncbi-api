# tests/test_import_refseq.py
import pytest
from datetime import date
from scripts.import_refseq import na_to_none, parse_row


def test_na_to_none_converts_na_to_none():
    assert na_to_none("na") is None


def test_na_to_none_converts_empty_string_to_none():
    assert na_to_none("") is None


def test_na_to_none_passes_through_real_values():
    assert na_to_none("GCF_000005845.2") == "GCF_000005845.2"


def make_raw_row(**overrides):
    """A minimal but complete row matching the real NCBI column set,
    with sensible defaults, so each test only needs to override what it cares about."""
    row = {
        "assembly_accession": "GCF_000005845.2",
        "bioproject": "PRJNA57779",
        "biosample": "SAMN02604091",
        "taxid": "511145",
        "species_taxid": "1260",
        "organism_name": "Escherichia coli str. K-12 substr. MG1655",
        "assembly_level": "Complete Genome",
        "asm_name": "ASM584v2",
        "asm_submitter": "Univ. Wisconsin",
        "genome_size": "4641652",
        "contig_count": "1",
        "gc_percent": "51.000000",
        "seq_rel_date": "2013-09-26",
    }
    row.update(overrides)
    return row


def test_parse_row_maps_real_values_correctly():
    row = make_raw_row()
    result = parse_row(row)

    assert result["accession"] == "GCF_000005845.2"
    assert result["organism_name"] == "Escherichia coli str. K-12 substr. MG1655"
    assert result["tax_id"] == 511145
    assert result["species_tax_id"] == 1260
    assert result["total_sequence_length"] == 4641652
    assert result["number_of_contigs"] == 1
    assert result["gc_percent"] == 51.0
    assert result["submission_date"] == date(2013, 9, 26)


def test_parse_row_handles_na_values_as_none():
    row = make_raw_row(
        bioproject="na",
        genome_size="na",
        gc_percent="na",
        seq_rel_date="na",
    )
    result = parse_row(row)

    assert result["bioproject_accession"] is None
    assert result["total_sequence_length"] is None
    assert result["gc_percent"] is None
    assert result["submission_date"] is None


def test_parse_row_raises_on_malformed_numeric_field():
    # Simulates the exact bug we hit: a shifted column putting
    # a non-numeric string where a number was expected.
    row = make_raw_row(genome_size="bacteria")

    with pytest.raises(ValueError):
        parse_row(row)