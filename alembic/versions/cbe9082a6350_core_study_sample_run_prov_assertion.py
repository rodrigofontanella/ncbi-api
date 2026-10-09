"""core study/sample/run, prov.assertion

Revision ID: cbe9082a6350
Revises: bc88c839e754
Create Date: 2026-10-09 10:33:07.242359

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cbe9082a6350'
down_revision: Union[str, Sequence[str], None] = 'bc88c839e754'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Order matters: an enum compares by position, so curated > derived > asserted > inferred.
TIERS = ("inferred", "asserted", "derived", "curated")
evidence_tier = postgresql.ENUM(*TIERS, name="evidence_tier", schema="prov", create_type=False)


def ingest_run_fk():
    """Every row records which load created it."""
    return sa.Column("ingest_run_id", sa.BigInteger,
                     sa.ForeignKey("prov.ingest_run.ingest_run_id"), nullable=False)


def created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                     server_default=sa.text("now()"))


def upgrade() -> None:
    # ── core.study: one row per BioProject (or private study) ───────────────
    op.create_table(
        "study",
        sa.Column("study_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("bioproject_acc", sa.Text),      # PRJNA… / PRJEB… / PRJDB…
        sa.Column("local_id", sa.Text),            # private studies, namespaced: 'nutreco:boxmeer-2025'
        sa.Column("title", sa.Text),
        sa.Column("description", sa.Text),
        ingest_run_fk(),
        created_at(),
        sa.UniqueConstraint("bioproject_acc", name="study_bioproject_acc_key"),
        sa.UniqueConstraint("local_id", name="study_local_id_key"),
        sa.CheckConstraint("bioproject_acc IS NOT NULL OR local_id IS NOT NULL", name="study_has_key"),
        schema="core",
    )

    # ── core.sample: one row per BioSample (the canonical key) ─────────────
    op.create_table(
        "sample",
        sa.Column("sample_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("biosample_acc", sa.Text),       # SAMN / SAMEA / SAMD
        sa.Column("sra_sample_acc", sa.Text),      # SRS / ERS / DRS
        sa.Column("local_id", sa.Text),            # samples with no BioSample, namespaced: 'upgg:CN-farm3-12'
        ingest_run_fk(),
        created_at(),
        sa.UniqueConstraint("biosample_acc", name="sample_biosample_acc_key"),
        sa.UniqueConstraint("sra_sample_acc", name="sample_sra_sample_acc_key"),
        sa.UniqueConstraint("local_id", name="sample_local_id_key"),
        sa.CheckConstraint("num_nonnulls(biosample_acc, sra_sample_acc, local_id) >= 1", name="sample_has_key"),
        schema="core",
    )

    # ── core.study_sample: a BioSample can belong to more than one BioProject ─
    op.create_table(
        "study_sample",
        sa.Column("study_id", sa.BigInteger, sa.ForeignKey("core.study.study_id"), primary_key=True),
        sa.Column("sample_id", sa.BigInteger, sa.ForeignKey("core.sample.sample_id"), primary_key=True),
        ingest_run_fk(),
        sa.Index("study_sample_sample_id_idx", "sample_id"),
        schema="core",
    )

    # ── core.run: one row per SRA/ENA run. Technical columns = what SRA reports ─
    op.create_table(
        "run",
        sa.Column("run_acc", sa.Text, primary_key=True),          # SRR / ERR / DRR
        sa.Column("sample_id", sa.BigInteger, sa.ForeignKey("core.sample.sample_id"), nullable=False),
        sa.Column("study_id", sa.BigInteger, sa.ForeignKey("core.study.study_id"), nullable=False),
        sa.Column("library_strategy", sa.Text),   # AMPLICON | WGS | …
        sa.Column("library_source", sa.Text),     # METAGENOMIC | GENOMIC | …
        sa.Column("library_layout", sa.Text),
        sa.Column("platform", sa.Text),           # ILLUMINA | LS454 | ION_TORRENT | OXFORD_NANOPORE | PACBIO_SMRT
        sa.Column("instrument_model", sa.Text),   # 'Illumina MiSeq', …
        sa.Column("spots", sa.BigInteger),
        sa.Column("bases", sa.BigInteger),
        sa.Column("avg_read_len", sa.Integer),
        sa.Column("release_date", sa.Date),
        ingest_run_fk(),
        created_at(),
        sa.CheckConstraint("library_layout IN ('SINGLE','PAIRED')", name="run_layout_check"),
        sa.Index("run_sample_id_idx", "sample_id"),
        sa.Index("run_study_id_idx", "study_id"),
        schema="core",
    )

    # ── prov.assertion: every descriptive fact, with where it came from ─────
    op.execute("CREATE TYPE prov.evidence_tier AS ENUM ('inferred', 'asserted', 'derived', 'curated')")
    op.create_table(
        "assertion",
        sa.Column("assertion_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        # exactly one of these four says WHAT the fact is about (an "exclusive arc"; real FKs, unlike entity_type+entity_id)
        sa.Column("study_id", sa.BigInteger, sa.ForeignKey("core.study.study_id")),
        sa.Column("sample_id", sa.BigInteger, sa.ForeignKey("core.sample.sample_id")),
        sa.Column("run_acc", sa.Text, sa.ForeignKey("core.run.run_acc")),
        sa.Column("genome_acc", sa.String, sa.ForeignKey("ref.genome.accession")),
        sa.Column("field", sa.Text, nullable=False),        # 'gut_section', 'host_taxid', 'growth_stage', 'age_days_min', …
        sa.Column("value_text", sa.Text),                   # normalised text, e.g. 'Cecum'
        sa.Column("value_term", sa.Text),                   # ontology CURIE, e.g. 'UBERON:0001153'
        sa.Column("value_num", sa.Numeric),
        sa.Column("unit", sa.Text),
        sa.Column("tier", evidence_tier, nullable=False),
        sa.Column("method", sa.Text, nullable=False),       # 'pgmd_curation', 'biosample_attr:host', 'llm:qwen3@prompt_v1'
        sa.Column("evidence", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        ingest_run_fk(),
        created_at(),
        sa.CheckConstraint("num_nonnulls(study_id, sample_id, run_acc, genome_acc) = 1", name="assertion_one_entity"),
        sa.CheckConstraint("num_nonnulls(value_text, value_term, value_num) >= 1", name="assertion_has_value"),
        sa.Index("assertion_study_field_idx", "study_id", "field"),
        sa.Index("assertion_sample_field_idx", "sample_id", "field"),
        sa.Index("assertion_run_field_idx", "run_acc", "field"),
        sa.Index("assertion_genome_field_idx", "genome_acc", "field"),
        schema="prov",
    )


def downgrade() -> None:
    op.drop_table("assertion", schema="prov")
    op.execute("DROP TYPE prov.evidence_tier")
    op.drop_table("run", schema="core")
    op.drop_table("study_sample", schema="core")
    op.drop_table("sample", schema="core")
    op.drop_table("study", schema="core")
