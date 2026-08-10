"""Create the phase-1 visual workbench schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("material", sa.String(120)),
        sa.Column("color", sa.String(120)),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("weight_value", sa.Numeric(12, 3)),
        sa.Column("weight_unit", sa.String(16)),
        sa.Column("selling_points", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_products_category", "products", ["category"])

    op.create_table(
        "skus",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="CASCADE")),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_skus_product_id", "skus", ["product_id"])

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="CASCADE")),
        sa.Column("sku_id", sa.Uuid(), sa.ForeignKey("skus.id", ondelete="SET NULL")),
        sa.Column(
            "asset_type",
            sa.Enum(
                "ORIGINAL", "CUTOUT", "MAIN", "DETAIL", "DIMENSION", "SCENE",
                "USAGE", "PACKAGE", "CLOSEUP", "COMPARE", name="assettype"
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(200)),
        *timestamps(),
    )
    op.create_index("ix_assets_product_type", "assets", ["product_id", "asset_type"])

    op.create_table(
        "asset_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="CASCADE")),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column(
            "source_version_id",
            sa.Uuid(),
            sa.ForeignKey("asset_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("asset_id", "version_number"),
    )
    op.create_index("ix_asset_versions_checksum", "asset_versions", ["checksum_sha256"])

    op.create_table(
        "platform_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "platform",
            sa.Enum("TEMU", "AMAZON", "TIKTOK_SHOP", "SHOPEE", "ALIEXPRESS", name="platformcode"),
            nullable=False,
        ),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column(
            "image_slot",
            sa.Enum("MAIN", "DETAIL", "DIMENSION", "SCENE", "USAGE", "PACKAGE", "CLOSEUP", "COMPARE", name="imageslot"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "platform", "market", "category", "image_slot", "rule_version",
            name="uq_platform_rule_version",
        ),
    )
    op.create_index(
        "ix_platform_rule_resolution",
        "platform_rules",
        ["platform", "market", "category", "image_slot", "effective_date"],
    )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_version_id", sa.Uuid(), sa.ForeignKey("asset_versions.id", ondelete="RESTRICT")),
        sa.Column("output_version_id", sa.Uuid(), sa.ForeignKey("asset_versions.id", ondelete="SET NULL")),
        sa.Column("resolved_rule_id", sa.Uuid(), sa.ForeignKey("platform_rules.id", ondelete="RESTRICT")),
        sa.Column("platform", sa.Enum(name="platformcode", create_type=False), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("image_slot", sa.Enum(name="imageslot", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="jobstatus"), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_generation_jobs_status_created", "generation_jobs", ["status", "created_at"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_version_id", sa.Uuid(), sa.ForeignKey("asset_versions.id", ondelete="RESTRICT")),
        sa.Column("generation_job_id", sa.Uuid(), sa.ForeignKey("generation_jobs.id", ondelete="RESTRICT")),
        sa.Column("decision", sa.Enum("APPROVED", "REJECTED", "REGENERATE", name="reviewdecision"), nullable=False),
        sa.Column("reviewer", sa.String(120), nullable=False),
        sa.Column("comment", sa.Text()),
        *timestamps(),
    )
    op.create_index("ix_reviews_version_created", "reviews", ["asset_version_id", "created_at"])

    op.create_table(
        "export_bundles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT")),
        sa.Column("platform", sa.Enum(name="platformcode", create_type=False), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.Enum("READY", "FAILED", name="exportstatus"), nullable=False),
        *timestamps(),
    )


def downgrade() -> None:
    op.drop_table("export_bundles")
    op.drop_table("reviews")
    op.drop_table("generation_jobs")
    op.drop_table("platform_rules")
    op.drop_table("asset_versions")
    op.drop_table("assets")
    op.drop_table("skus")
    op.drop_table("products")
    for enum_name in [
        "exportstatus", "reviewdecision", "jobstatus", "imageslot", "platformcode", "assettype"
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)

