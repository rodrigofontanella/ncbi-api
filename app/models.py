# app/models.py
from sqlalchemy import Text, ForeignKey, Identity, CheckConstraint, text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, ENUM
from sqlalchemy import String, Integer, BigInteger, Numeric, Date, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from typing import Optional
from datetime import date, datetime


class Base(DeclarativeBase):
    pass


class IngestRun(Base):
    __tablename__ = "ingest_run"
    __table_args__ = (
        CheckConstraint("source IN ('ncbi','microbeatlas','micoda','pgmd','bacdive','europepmc','docs','manual','own')",
                        name="ingest_run_source_check"),
        {"schema": "prov"},
    )

    ingest_run_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_release: Mapped[Optional[str]] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    raw_uri: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Assembly(Base):
    """Genome metadata, stored in ref.genome. Class name kept so routers and scripts don't change."""
    __tablename__ = "genome"
    __table_args__ = (
        CheckConstraint("source IN ('ncbi','pigc','upgg','gtdb')", name="genome_source_check"),
        CheckConstraint("domain IN ('Bacteria','Archaea','Fungi','Other')", name="genome_domain_check"),
        {"schema": "ref"},
    )

    accession: Mapped[str] = mapped_column(String, primary_key=True)
    organism_name: Mapped[str] = mapped_column(String, nullable=False)
    tax_id: Mapped[Optional[int]] = mapped_column(Integer)
    species_tax_id: Mapped[Optional[int]] = mapped_column(Integer)
    assembly_level: Mapped[Optional[str]] = mapped_column(String)
    assembly_name: Mapped[Optional[str]] = mapped_column(String)
    submitter: Mapped[Optional[str]] = mapped_column(String)
    bioproject_accession: Mapped[Optional[str]] = mapped_column(String)
    biosample_accession: Mapped[Optional[str]] = mapped_column(String)
    contig_n50: Mapped[Optional[int]] = mapped_column(Integer)
    total_sequence_length: Mapped[Optional[int]] = mapped_column(BigInteger)
    number_of_contigs: Mapped[Optional[int]] = mapped_column(Integer)
    gc_percent: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    submission_date: Mapped[Optional[date]] = mapped_column(Date)
    checkm_completeness: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    checkm_contamination: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    ani_best_match_organism: Mapped[Optional[str]] = mapped_column(String)
    ani_best_match_percent: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="ncbi")
    domain: Mapped[Optional[str]] = mapped_column(Text)
    gtdb_taxonomy: Mapped[Optional[str]] = mapped_column(Text)
    gtdb_release: Mapped[Optional[str]] = mapped_column(Text)
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    sha256: Mapped[Optional[str]] = mapped_column(Text)
    ingest_run_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("prov.ingest_run.ingest_run_id", name="genome_ingest_run_fk"))


    # ── catalog core (migration: core study/sample/run, prov.assertion) ─────────

EVIDENCE_TIER = ENUM("inferred", "asserted", "derived", "curated", name="evidence_tier", schema="prov")


class Study(Base):
    __tablename__ = "study"
    __table_args__ = (
        UniqueConstraint("bioproject_acc", name="study_bioproject_acc_key"),
        UniqueConstraint("local_id", name="study_local_id_key"),
        CheckConstraint("bioproject_acc IS NOT NULL OR local_id IS NOT NULL", name="study_has_key"),
        {"schema": "core"},
    )

    study_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    bioproject_acc: Mapped[Optional[str]] = mapped_column(Text)
    local_id: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    ingest_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("prov.ingest_run.ingest_run_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Sample(Base):
    __tablename__ = "sample"
    __table_args__ = (
        UniqueConstraint("biosample_acc", name="sample_biosample_acc_key"),
        UniqueConstraint("sra_sample_acc", name="sample_sra_sample_acc_key"),
        UniqueConstraint("local_id", name="sample_local_id_key"),
        CheckConstraint("num_nonnulls(biosample_acc, sra_sample_acc, local_id) >= 1", name="sample_has_key"),
        {"schema": "core"},
    )

    sample_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    biosample_acc: Mapped[Optional[str]] = mapped_column(Text)
    sra_sample_acc: Mapped[Optional[str]] = mapped_column(Text)
    local_id: Mapped[Optional[str]] = mapped_column(Text)
    ingest_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("prov.ingest_run.ingest_run_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class StudySample(Base):
    __tablename__ = "study_sample"
    __table_args__ = (
        Index("study_sample_sample_id_idx", "sample_id"),
        {"schema": "core"},
    )

    study_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core.study.study_id"), primary_key=True)
    sample_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core.sample.sample_id"), primary_key=True)
    ingest_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("prov.ingest_run.ingest_run_id"), nullable=False)


class Run(Base):
    __tablename__ = "run"
    __table_args__ = (
        CheckConstraint("library_layout IN ('SINGLE','PAIRED')", name="run_layout_check"),
        Index("run_sample_id_idx", "sample_id"),
        Index("run_study_id_idx", "study_id"),
        {"schema": "core"},
    )

    run_acc: Mapped[str] = mapped_column(Text, primary_key=True)
    sample_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core.sample.sample_id"), nullable=False)
    study_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core.study.study_id"), nullable=False)
    library_strategy: Mapped[Optional[str]] = mapped_column(Text)
    library_source: Mapped[Optional[str]] = mapped_column(Text)
    library_layout: Mapped[Optional[str]] = mapped_column(Text)
    platform: Mapped[Optional[str]] = mapped_column(Text)
    instrument_model: Mapped[Optional[str]] = mapped_column(Text)
    spots: Mapped[Optional[int]] = mapped_column(BigInteger)
    bases: Mapped[Optional[int]] = mapped_column(BigInteger)
    avg_read_len: Mapped[Optional[int]] = mapped_column(Integer)
    release_date: Mapped[Optional[date]] = mapped_column(Date)
    ingest_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("prov.ingest_run.ingest_run_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Assertion(Base):
    __tablename__ = "assertion"
    __table_args__ = (
        CheckConstraint("num_nonnulls(study_id, sample_id, run_acc, genome_acc) = 1", name="assertion_one_entity"),
        CheckConstraint("num_nonnulls(value_text, value_term, value_num) >= 1", name="assertion_has_value"),
        Index("assertion_study_field_idx", "study_id", "field"),
        Index("assertion_sample_field_idx", "sample_id", "field"),
        Index("assertion_run_field_idx", "run_acc", "field"),
        Index("assertion_genome_field_idx", "genome_acc", "field"),
        {"schema": "prov"},
    )

    assertion_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    study_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("core.study.study_id"))
    sample_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("core.sample.sample_id"))
    run_acc: Mapped[Optional[str]] = mapped_column(Text, ForeignKey("core.run.run_acc"))
    genome_acc: Mapped[Optional[str]] = mapped_column(String, ForeignKey("ref.genome.accession"))
    field: Mapped[str] = mapped_column(Text, nullable=False)
    value_text: Mapped[Optional[str]] = mapped_column(Text)
    value_term: Mapped[Optional[str]] = mapped_column(Text)
    value_num: Mapped[Optional[float]] = mapped_column(Numeric)
    unit: Mapped[Optional[str]] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(EVIDENCE_TIER, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ingest_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("prov.ingest_run.ingest_run_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())