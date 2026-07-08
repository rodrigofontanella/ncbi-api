# app/models.py
from sqlalchemy import String, Integer, BigInteger, Numeric, Date, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from typing import Optional
from datetime import date, datetime

class Base(DeclarativeBase):
    pass

class Assembly(Base):
    __tablename__ = "assemblies"

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