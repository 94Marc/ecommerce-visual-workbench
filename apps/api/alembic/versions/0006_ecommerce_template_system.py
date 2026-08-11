"""Add versioned ecommerce templates and deterministic render traceability."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_ecommerce_template_system"
down_revision: str | None = "0005_real_image_processing_providers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

template_type = sa.Enum(
    "MAIN",
    "DETAIL",
    "DIMENSION",
    "SELLING_POINT",
    "PARAMETER",
    "PACKAGE",
    "COMPARE",
    name="templatetype",
)
template_status = sa.Enum("DRAFT", "ACTIVE", "ARCHIVED", name="templatestatus")
provider_type = sa.Enum("AI", "IMAGE_PROCESSING", "TEMPLATE", name="providertype")

RENDER_TASKS = (
    "RENDER_MAIN_TEMPLATE",
    "RENDER_DIMENSION_TEMPLATE",
    "RENDER_DETAIL_TEMPLATE",
    "RENDER_SELLING_POINT_TEMPLATE",
    "RENDER_PARAMETER_TEMPLATE",
    "RENDER_PACKAGE_TEMPLATE",
    "RENDER_COMPARE_TEMPLATE",
)


def upgrade() -> None:
    for task in RENDER_TASKS:
        op.execute(f"ALTER TYPE tasktype ADD VALUE IF NOT EXISTS '{task}'")

    op.create_table(
        "templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("template_type", template_type, nullable=False),
        sa.Column("status", template_status, nullable=False),
        sa.Column(
            "preview_asset_id",
            sa.Uuid(),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_templates_code", "templates", ["code"], unique=True)
    op.create_index("ix_templates_template_type", "templates", ["template_type"])
    op.create_index("ix_templates_status", "templates", ["status"])

    op.create_table(
        "template_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("canvas_width", sa.Integer(), nullable=False),
        sa.Column("canvas_height", sa.Integer(), nullable=False),
        sa.Column("background", sa.JSON(), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("template_id", "version"),
    )
    op.create_index("ix_template_versions_template_id", "template_versions", ["template_id"])

    provider_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "generation_jobs",
        sa.Column("provider_type", provider_type, nullable=False, server_default="AI"),
    )
    op.create_index("ix_generation_jobs_provider_type", "generation_jobs", ["provider_type"])
    op.execute(
        "UPDATE generation_jobs SET provider_type='IMAGE_PROCESSING' "
        "WHERE task_type::text IN ('REMOVE_BACKGROUND','UPSCALE')"
    )

    op.add_column(
        "asset_slots",
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_asset_slots_template_id", "asset_slots", ["template_id"])

    op.create_table(
        "template_render_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "template_version_id",
            sa.Uuid(),
            sa.ForeignKey("template_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "generation_job_id",
            sa.Uuid(),
            sa.ForeignKey("generation_jobs.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "output_asset_version_id",
            sa.Uuid(),
            sa.ForeignKey("asset_versions.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sku_id", sa.Uuid(), sa.ForeignKey("skus.id", ondelete="SET NULL")),
        sa.Column("source_asset_version_ids", sa.JSON(), nullable=False),
        sa.Column("product_data_snapshot", sa.JSON(), nullable=False),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "template_id",
        "template_version_id",
        "generation_job_id",
        "output_asset_version_id",
        "product_id",
    ):
        op.create_index(f"ix_template_render_records_{column}", "template_render_records", [column])


def downgrade() -> None:
    op.drop_table("template_render_records")
    op.drop_index("ix_asset_slots_template_id", table_name="asset_slots")
    op.drop_column("asset_slots", "template_id")
    op.drop_index("ix_generation_jobs_provider_type", table_name="generation_jobs")
    op.drop_column("generation_jobs", "provider_type")
    provider_type.drop(op.get_bind(), checkfirst=True)
    op.drop_table("template_versions")
    op.drop_table("templates")
    template_status.drop(op.get_bind(), checkfirst=True)
    template_type.drop(op.get_bind(), checkfirst=True)
