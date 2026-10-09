"""core study/subject/sample/library/run, prov.assertion

Revision ID: 5fa98eb29c21
Revises: bc88c839e754
Create Date: 2026-10-09 14:44:25.293703

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5fa98eb29c21'
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
 
    # ── core.subject: the animal. The biological unit, not the sequencing run ─
    op.create_table(
        "subject",
        sa.Column("subject_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("study_id", sa.BigInteger, sa.ForeignKey("core.study.study_id"), nullable=False),
        sa.Column("local_id", sa.Text, nullable=False),   # BioSample host_subject_id, ear tag, 'P001' (unique within the study)
        sa.Column("host_taxid", sa.Integer),              # 9823 pig, 9031 chicken; FK to core.taxon once it exists
        sa.Column("pen", sa.Text),                        # housing unit label within the study: often the true experimental unit
        sa.Column("litter", sa.Text),                     # litter / dam label within the study: piglets are nested in litters
        ingest_run_fk(),
        created_at(),
        sa.UniqueConstraint("study_id", "local_id", name="subject_study_local_id_key"),
        schema="core",
    )
 
    # ── core.sample: one row per BioSample = one specimen (pig P001 / cecum) ─
    op.create_table(
        "sample",
        sa.Column("sample_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("biosample_acc", sa.Text),       # SAMN / SAMEA / SAMD
        sa.Column("sra_sample_acc", sa.Text),      # SRS / ERS / DRS
        sa.Column("local_id", sa.Text),            # samples with no BioSample, namespaced: 'upgg:CN-farm3-12'
        sa.Column("subject_id", sa.BigInteger, sa.ForeignKey("core.subject.subject_id")),  # NULL when the animal is unknown
        ingest_run_fk(),
        created_at(),
        sa.UniqueConstraint("biosample_acc", name="sample_biosample_acc_key"),
        sa.UniqueConstraint("sra_sample_acc", name="sample_sra_sample_acc_key"),
        sa.UniqueConstraint("local_id", name="sample_local_id_key"),
        sa.CheckConstraint("num_nonnulls(biosample_acc, sra_sample_acc, local_id) >= 1", name="sample_has_key"),
        sa.Index("sample_subject_id_idx", "subject_id"),
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
 
    # ── core.library: one row per SRA experiment (SRX) = one library prep ───
    #    Library descriptors live here because that is where SRA records them.
    op.create_table(
        "library",
        sa.Column("library_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("experiment_acc", sa.Text),     # SRX / ERX / DRX
        sa.Column("local_id", sa.Text),           # own libraries before submission: 'own:LIB-2026-001'
        sa.Column("sample_id", sa.BigInteger, sa.ForeignKey("core.sample.sample_id"), nullable=False),
        sa.Column("study_id", sa.BigInteger, sa.ForeignKey("core.study.study_id"), nullable=False),
        sa.Column("library_name", sa.Text),
        sa.Column("library_strategy", sa.Text),   # AMPLICON | WGS | …
        sa.Column("library_source", sa.Text),     # METAGENOMIC | GENOMIC | …
        sa.Column("library_selection", sa.Text),  # PCR | RANDOM | …
        sa.Column("library_layout", sa.Text),
        sa.Column("platform", sa.Text),           # ILLUMINA | LS454 | ION_TORRENT | OXFORD_NANOPORE | PACBIO_SMRT
        sa.Column("instrument_model", sa.Text),   # 'Illumina MiSeq', …
        ingest_run_fk(),
        created_at(),
        sa.UniqueConstraint("experiment_acc", name="library_experiment_acc_key"),
        sa.UniqueConstraint("local_id", name="library_local_id_key"),
        sa.UniqueConstraint("library_id", "sample_id", name="library_id_sample_key"),   # target of run's composite FK
        sa.CheckConstraint("experiment_acc IS NOT NULL OR local_id IS NOT NULL", name="library_has_key"),
        sa.CheckConstraint("library_layout IN ('SINGLE','PAIRED')", name="library_layout_check"),
        sa.Index("library_sample_id_idx", "sample_id"),
        schema="core",
    )
 
    # ── core.run: one row per SRA/ENA run (SRR). Sequencing output of a library ─
    #    sample_id/study_id are what every source gives (PGMD has no SRX);
    #    library_id is filled once SRA run info is loaded. The composite FK makes it
    #    impossible for a run to point at a library of a *different* sample.
    op.create_table(
        "run",
        sa.Column("run_acc", sa.Text, primary_key=True),          # SRR / ERR / DRR
        sa.Column("sample_id", sa.BigInteger, sa.ForeignKey("core.sample.sample_id"), nullable=False),
        sa.Column("study_id", sa.BigInteger, sa.ForeignKey("core.study.study_id"), nullable=False),
        sa.Column("library_id", sa.BigInteger),
        sa.Column("spots", sa.BigInteger),
        sa.Column("bases", sa.BigInteger),
        sa.Column("avg_read_len", sa.Integer),
        sa.Column("release_date", sa.Date),
        ingest_run_fk(),
        created_at(),
        sa.ForeignKeyConstraint(["library_id", "sample_id"], ["core.library.library_id", "core.library.sample_id"],
                                name="run_library_fk"),
        sa.Index("run_sample_id_idx", "sample_id"),
        sa.Index("run_study_id_idx", "study_id"),
        sa.Index("run_library_id_idx", "library_id"),
        schema="core",
    )
 
    # ── prov.assertion: every descriptive fact, with where it came from ─────
    op.execute("CREATE TYPE prov.evidence_tier AS ENUM ('inferred', 'asserted', 'derived', 'curated')")
    op.create_table(
        "assertion",
        sa.Column("assertion_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        # exactly one of these six says WHAT the fact is about ("exclusive arc": every target is a real FK)
        sa.Column("study_id", sa.BigInteger, sa.ForeignKey("core.study.study_id")),
        sa.Column("subject_id", sa.BigInteger, sa.ForeignKey("core.subject.subject_id")),
        sa.Column("sample_id", sa.BigInteger, sa.ForeignKey("core.sample.sample_id")),
        sa.Column("library_id", sa.BigInteger, sa.ForeignKey("core.library.library_id")),
        sa.Column("run_acc", sa.Text, sa.ForeignKey("core.run.run_acc")),
        sa.Column("genome_acc", sa.String, sa.ForeignKey("ref.genome.accession")),
        sa.Column("field", sa.Text, nullable=False),        # 'gut_section', 'sex', 'breed', 'target_region', …
        sa.Column("value_text", sa.Text),                   # normalised text, e.g. 'Cecum'
        sa.Column("value_term", sa.Text),                   # ontology CURIE, e.g. 'UBERON:0001153'
        sa.Column("value_num", sa.Numeric),
        sa.Column("unit", sa.Text),
        sa.Column("tier", evidence_tier, nullable=False),
        sa.Column("method", sa.Text, nullable=False),       # 'pgmd_curation', 'biosample_attr:host', 'llm:qwen@prompt_v1'
        sa.Column("evidence", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        ingest_run_fk(),
        created_at(),
        sa.CheckConstraint("num_nonnulls(study_id, subject_id, sample_id, library_id, run_acc, genome_acc) = 1",
                           name="assertion_one_entity"),
        sa.CheckConstraint("num_nonnulls(value_text, value_term, value_num) >= 1", name="assertion_has_value"),
        sa.Index("assertion_study_field_idx", "study_id", "field"),
        sa.Index("assertion_subject_field_idx", "subject_id", "field"),
        sa.Index("assertion_sample_field_idx", "sample_id", "field"),
        sa.Index("assertion_library_field_idx", "library_id", "field"),
        sa.Index("assertion_run_field_idx", "run_acc", "field"),
        sa.Index("assertion_genome_field_idx", "genome_acc", "field"),
        schema="prov",
    )
 
 
def downgrade() -> None:
    op.drop_table("assertion", schema="prov")
    op.execute("DROP TYPE prov.evidence_tier")
    op.drop_table("run", schema="core")
    op.drop_table("library", schema="core")
    op.drop_table("study_sample", schema="core")
    op.drop_table("sample", schema="core")
    op.drop_table("subject", schema="core")
    op.drop_table("study", schema="core")
