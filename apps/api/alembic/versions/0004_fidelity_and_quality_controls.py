"""Add product fidelity controls, multi-reference tasks and quality checks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_fidelity_and_quality_controls"
down_revision: str | None = "0003_real_generation_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

generation_mode = sa.Enum("STRICT", "BALANCED", "CREATIVE", name="generationmode")
reject_reason = sa.Enum(
    "PRODUCT_CHANGED",
    "WRONG_COLOR",
    "WRONG_TEXTURE",
    "WRONG_SHAPE",
    "UNREALISTIC_USAGE",
    "AI_ARTIFACT",
    "TEXT_ERROR",
    "SIZE_ERROR",
    "PACKAGING_ERROR",
    "OTHER",
    name="rejectreason",
)


def upgrade() -> None:
    generation_mode.create(op.get_bind(), checkfirst=True)
    reject_reason.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "generation_jobs",
        sa.Column(
            "generation_mode",
            generation_mode,
            nullable=False,
            server_default="STRICT",
        ),
    )
    op.add_column(
        "generation_jobs",
        sa.Column(
            "reference_asset_version_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column("generation_jobs", sa.Column("revised_prompt", sa.Text()))
    op.add_column("generation_jobs", sa.Column("duration_ms", sa.Integer()))
    op.add_column("generation_attempts", sa.Column("duration_ms", sa.Integer()))
    op.add_column("reviews", sa.Column("reason", reject_reason, nullable=True))
    op.create_index("ix_generation_jobs_generation_mode", "generation_jobs", ["generation_mode"])
    op.execute(
        "UPDATE generation_jobs SET reference_asset_version_ids="
        "json_build_array(source_version_id::text)"
    )
    op.execute(
        "UPDATE generation_jobs SET generation_mode='BALANCED' "
        "WHERE image_slot::text IN ('SCENE','USAGE')"
    )
    op.execute(
        "UPDATE generation_jobs SET generation_mode='CREATIVE' "
        "WHERE image_slot::text NOT IN "
        "('MAIN','DETAIL','DIMENSION','PACKAGE','CLOSEUP','SCENE','USAGE')"
    )

    op.create_table(
        "generation_quality_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "generation_job_id",
            sa.Uuid(),
            sa.ForeignKey("generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "output_version_id",
            sa.Uuid(),
            sa.ForeignKey("asset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_similarity", sa.JSON(), nullable=False),
        sa.Column("resolution", sa.JSON(), nullable=False),
        sa.Column("aspect_ratio", sa.JSON(), nullable=False),
        sa.Column("file_size", sa.JSON(), nullable=False),
        sa.Column("format", sa.JSON(), nullable=False),
        sa.Column("text_risk", sa.JSON(), nullable=False),
        sa.Column("watermark_risk", sa.JSON(), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_generation_quality_checks_generation_job_id",
        "generation_quality_checks",
        ["generation_job_id"],
    )
    op.create_index(
        "ix_generation_quality_checks_output_version_id",
        "generation_quality_checks",
        ["output_version_id"],
    )


def downgrade() -> None:
    op.drop_table("generation_quality_checks")
    op.drop_index("ix_generation_jobs_generation_mode", table_name="generation_jobs")
    op.drop_column("reviews", "reason")
    op.drop_column("generation_attempts", "duration_ms")
    for column in [
        "duration_ms",
        "revised_prompt",
        "reference_asset_version_ids",
        "generation_mode",
    ]:
        op.drop_column("generation_jobs", column)
    reject_reason.drop(op.get_bind(), checkfirst=True)
    generation_mode.drop(op.get_bind(), checkfirst=True)
