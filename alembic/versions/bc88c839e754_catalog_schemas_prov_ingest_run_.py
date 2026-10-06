"""catalog schemas, prov.ingest_run, assemblies to ref.genome

Revision ID: bc88c839e754
Revises: c2aba1132a27
Create Date: 2026-10-06 18:44:35.512495

"""

"""catalog schemas, prov.ingest_run, assemblies to ref.genome

Revision ID: bc88c839e754
Revises: c2aba1132a27
"""
from typing import Sequence, Union

revision: str = 'bc88c839e754'
down_revision: Union[str, Sequence[str], None] = 'c2aba1132a27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


SCHEMAS = ("staging", "core", "prov", "rag", "ref")

# Grants only where the roles exist: this migration must also run on the
# docker dev DB (ncbi_db), where microbio_app / microbio_ro don't exist.
GRANTS = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'microbio_app') THEN
    GRANT USAGE ON SCHEMA staging, core, prov, rag, ref TO microbio_app;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'microbio_ro') THEN
    GRANT USAGE ON SCHEMA core, prov, rag, ref TO microbio_ro;   -- no staging: raw payloads aren't for the agent
  END IF;
END
$$;
"""

INGEST_SOURCES = "('ncbi','microbeatlas','micoda','pgmd','bacdive','europepmc','docs','manual','own')"


def upgrade() -> None:
    # 1. schemas + who may use them (table-level grants come from the DEFAULT PRIVILEGES set in §5)
    for s in SCHEMAS:
        op.execute(f"CREATE SCHEMA {s}")
    op.execute(GRANTS)

    # 2. provenance: every load, import or pipeline run gets one row here
    op.create_table(
        "ingest_run",
        sa.Column("ingest_run_id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_release", sa.Text),
        sa.Column("params", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_uri", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"source IN {INGEST_SOURCES}", name="ingest_run_source_check"),
        schema="prov",
    )

    # 3. move, don't recreate: existing rows (dev DB) survive, grants travel with the table
    op.execute("ALTER TABLE public.assemblies SET SCHEMA ref")
    op.rename_table("assemblies", "genome", schema="ref")
    op.execute("ALTER INDEX ref.assemblies_pkey RENAME TO genome_pkey")

    # 4. new columns for the catalog (design doc §5.1)
    op.add_column("genome", sa.Column("source", sa.Text, nullable=False, server_default="ncbi"), schema="ref")
    op.add_column("genome", sa.Column("domain", sa.Text), schema="ref")
    op.add_column("genome", sa.Column("gtdb_taxonomy", sa.Text), schema="ref")
    op.add_column("genome", sa.Column("gtdb_release", sa.Text), schema="ref")
    op.add_column("genome", sa.Column("file_path", sa.Text), schema="ref")
    op.add_column("genome", sa.Column("sha256", sa.Text), schema="ref")
    op.add_column("genome", sa.Column("ingest_run_id", sa.BigInteger), schema="ref")
    op.create_check_constraint("genome_source_check", "genome",
                               "source IN ('ncbi','pigc','upgg','gtdb')", schema="ref")
    op.create_check_constraint("genome_domain_check", "genome",
                               "domain IN ('Bacteria','Archaea','Fungi','Other')", schema="ref")
    op.create_foreign_key("genome_ingest_run_fk", "genome", "ingest_run",
                          ["ingest_run_id"], ["ingest_run_id"],
                          source_schema="ref", referent_schema="prov")


def downgrade() -> None:
    # Lossy for the 7 new columns (they're empty today). Everything else is restored exactly.
    op.drop_constraint("genome_ingest_run_fk", "genome", schema="ref", type_="foreignkey")
    op.drop_constraint("genome_domain_check", "genome", schema="ref", type_="check")
    op.drop_constraint("genome_source_check", "genome", schema="ref", type_="check")
    for col in ("ingest_run_id", "sha256", "file_path", "gtdb_release", "gtdb_taxonomy", "domain", "source"):
        op.drop_column("genome", col, schema="ref")
    op.execute("ALTER INDEX ref.genome_pkey RENAME TO assemblies_pkey")
    op.rename_table("genome", "assemblies", schema="ref")
    op.execute("ALTER TABLE ref.assemblies SET SCHEMA public")
    op.drop_table("ingest_run", schema="prov")
    for s in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA {s}")   # no CASCADE on purpose: fails loudly if anything else lives there