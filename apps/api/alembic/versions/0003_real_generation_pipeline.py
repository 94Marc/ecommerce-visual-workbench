"""Add provider-backed generation jobs, attempts, slots and validation results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_real_generation_pipeline"
down_revision: str | None = "0002_platform_rules_and_visual_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

validation_status = sa.Enum("PENDING", "PASSED", "FAILED", name="validationstatus")
attempt_status = sa.Enum("PROCESSING", "COMPLETED", "FAILED", name="attemptstatus")


def upgrade() -> None:
    validation_status.create(op.get_bind(), checkfirst=True)
    op.add_column("generation_jobs", sa.Column("visual_plan_id", sa.Uuid(), nullable=True))
    op.add_column("generation_jobs", sa.Column("asset_slot_id", sa.Uuid(), nullable=True))
    op.add_column("generation_jobs", sa.Column("parent_job_id", sa.Uuid(), nullable=True))
    op.add_column(
        "generation_jobs",
        sa.Column("provider", sa.String(32), nullable=False, server_default="mock"),
    )
    op.add_column("generation_jobs", sa.Column("provider_model", sa.String(120)))
    op.add_column("generation_jobs", sa.Column("provider_request_id", sa.String(160)))
    op.add_column(
        "generation_jobs", sa.Column("prompt", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "generation_jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("generation_jobs", sa.Column("failure_code", sa.String(80)))
    op.add_column(
        "generation_jobs",
        sa.Column(
            "validation_status",
            validation_status,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "generation_jobs",
        sa.Column(
            "validation_result",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.create_foreign_key(
        "generation_jobs_visual_plan_id_fkey",
        "generation_jobs",
        "product_visual_plans",
        ["visual_plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "generation_jobs_asset_slot_id_fkey",
        "generation_jobs",
        "asset_slots",
        ["asset_slot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "generation_jobs_parent_job_id_fkey",
        "generation_jobs",
        "generation_jobs",
        ["parent_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_generation_jobs_visual_plan_id", "generation_jobs", ["visual_plan_id"])
    op.create_index("ix_generation_jobs_asset_slot_id", "generation_jobs", ["asset_slot_id"])
    op.create_index("ix_generation_jobs_parent_job_id", "generation_jobs", ["parent_job_id"])
    op.create_index(
        "ix_generation_jobs_validation_status", "generation_jobs", ["validation_status"]
    )
    op.execute(
        "UPDATE generation_jobs SET validation_status='PASSED', "
        "validation_result='{\"valid\": true, \"violations\": []}'::json "
        "WHERE status='COMPLETED' AND output_version_id IS NOT NULL"
    )

    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "generation_job_id",
            sa.Uuid(),
            sa.ForeignKey("generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", attempt_status, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_model", sa.String(120)),
        sa.Column("provider_request_id", sa.String(160)),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("generation_job_id", "attempt_number"),
    )
    op.create_index(
        "ix_generation_attempts_generation_job_id",
        "generation_attempts",
        ["generation_job_id"],
    )
    op.create_index("ix_generation_attempts_status", "generation_attempts", ["status"])


def downgrade() -> None:
    op.drop_table("generation_attempts")
    for index_name in [
        "ix_generation_jobs_validation_status",
        "ix_generation_jobs_parent_job_id",
        "ix_generation_jobs_asset_slot_id",
        "ix_generation_jobs_visual_plan_id",
    ]:
        op.drop_index(index_name, table_name="generation_jobs")
    for constraint in [
        "generation_jobs_parent_job_id_fkey",
        "generation_jobs_asset_slot_id_fkey",
        "generation_jobs_visual_plan_id_fkey",
    ]:
        op.drop_constraint(constraint, "generation_jobs", type_="foreignkey")
    for column in [
        "validation_result",
        "validation_status",
        "failure_code",
        "retryable",
        "timeout_seconds",
        "max_attempts",
        "attempt_count",
        "prompt",
        "provider_request_id",
        "provider_model",
        "provider",
        "parent_job_id",
        "asset_slot_id",
        "visual_plan_id",
    ]:
        op.drop_column("generation_jobs", column)
    attempt_status.drop(op.get_bind(), checkfirst=True)
    validation_status.drop(op.get_bind(), checkfirst=True)
