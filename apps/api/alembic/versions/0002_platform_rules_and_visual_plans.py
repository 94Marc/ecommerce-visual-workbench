"""Normalize platform rules and add product visual plans."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_platform_rules_and_visual_plans"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.rename_table("platform_rules", "platform_rules_legacy")
    op.create_table(
        "platforms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
    )
    op.create_table(
        "platform_markets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "platform_id",
            sa.Uuid(),
            sa.ForeignKey("platforms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("platform_id", "code"),
    )
    op.create_table(
        "platform_categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "market_id",
            sa.Uuid(),
            sa.ForeignKey("platform_markets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("market_id", "code"),
    )
    op.create_table(
        "platform_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("platform_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_slot", sa.String(32), nullable=False),
        sa.Column("image_type", sa.String(32), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("category_id", "image_slot", "image_type"),
    )
    op.create_table(
        "rule_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "platform_rule_id",
            sa.Uuid(),
            sa.ForeignKey("platform_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("min_width", sa.Integer()),
        sa.Column("min_height", sa.Integer()),
        sa.Column("ratio", sa.String(32)),
        sa.Column("max_size", sa.Integer()),
        sa.Column("text_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("watermark_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("extra_constraints", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("platform_rule_id", "version"),
    )

    op.execute("""INSERT INTO platforms (id, code, name, enabled, created_at, updated_at) VALUES
      (gen_random_uuid(),'temu','Temu',true,now(),now()),(gen_random_uuid(),'amazon','Amazon',true,now(),now()),
      (gen_random_uuid(),'tiktok_shop','TikTok Shop',true,now(),now()),(gen_random_uuid(),'shopee','Shopee',true,now(),now()),
      (gen_random_uuid(),'aliexpress','AliExpress',true,now(),now())""")
    op.execute("""INSERT INTO platform_markets (id,platform_id,code,name,enabled,created_at,updated_at)
      SELECT gen_random_uuid(),p.id,x.market,x.market,true,now(),now() FROM (SELECT DISTINCT platform::text platform,market FROM platform_rules_legacy)x JOIN platforms p ON p.code=lower(x.platform)""")
    op.execute("""INSERT INTO platform_categories (id,market_id,code,name,enabled,created_at,updated_at)
      SELECT gen_random_uuid(),pm.id,x.category,x.category,true,now(),now() FROM (SELECT DISTINCT platform::text platform,market,category FROM platform_rules_legacy)x JOIN platforms p ON p.code=lower(x.platform) JOIN platform_markets pm ON pm.platform_id=p.id AND pm.code=x.market""")
    op.execute("""INSERT INTO platform_rules (id,category_id,image_slot,image_type,created_at,updated_at)
      SELECT gen_random_uuid(),pc.id,x.image_slot,x.image_slot,now(),now() FROM (SELECT DISTINCT platform::text platform,market,category,image_slot::text FROM platform_rules_legacy)x JOIN platforms p ON p.code=lower(x.platform) JOIN platform_markets pm ON pm.platform_id=p.id AND pm.code=x.market JOIN platform_categories pc ON pc.market_id=pm.id AND pc.code=x.category""")
    op.execute("""INSERT INTO rule_versions (id,platform_rule_id,version,effective_date,min_width,min_height,ratio,max_size,text_allowed,watermark_allowed,extra_constraints,enabled,created_at,updated_at)
      SELECT l.id,r.id,l.rule_version,l.effective_date,(l.constraints->>'min_width')::integer,(l.constraints->>'min_height')::integer,l.constraints->'aspect_ratios'->>0,
      CASE WHEN l.constraints->>'max_file_size_mb' IS NULL THEN NULL ELSE ((l.constraints->>'max_file_size_mb')::numeric*1048576)::integer END,
      COALESCE((l.constraints->>'text_allowed')::boolean,true),COALESCE((l.constraints->>'watermark_allowed')::boolean,false),l.constraints,l.enabled,l.created_at,l.updated_at
      FROM platform_rules_legacy l JOIN platforms p ON p.code=lower(l.platform::text) JOIN platform_markets pm ON pm.platform_id=p.id AND pm.code=l.market JOIN platform_categories pc ON pc.market_id=pm.id AND pc.code=l.category JOIN platform_rules r ON r.category_id=pc.id AND r.image_slot=l.image_slot::text""")
    op.drop_constraint(
        "generation_jobs_resolved_rule_id_fkey", "generation_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "generation_jobs_resolved_rule_id_fkey",
        "generation_jobs",
        "rule_versions",
        ["resolved_rule_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_table("platform_rules_legacy")

    op.create_table(
        "product_visual_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform_id",
            sa.Uuid(),
            sa.ForeignKey("platforms.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rule_version_id",
            sa.Uuid(),
            sa.ForeignKey("rule_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("requested_outputs", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "asset_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "product_visual_plan_id",
            sa.Uuid(),
            sa.ForeignKey("product_visual_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("image_type", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(160)),
        *timestamps(),
        sa.UniqueConstraint("product_visual_plan_id", "code"),
        sa.UniqueConstraint("product_visual_plan_id", "position"),
    )
    op.add_column("assets", sa.Column("asset_slot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "assets_asset_slot_id_fkey",
        "assets",
        "asset_slots",
        ["asset_slot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_assets_asset_slot_id", "assets", ["asset_slot_id"])


def downgrade() -> None:
    op.drop_constraint("uq_assets_asset_slot_id", "assets", type_="unique")
    op.drop_constraint("assets_asset_slot_id_fkey", "assets", type_="foreignkey")
    op.drop_column("assets", "asset_slot_id")
    op.drop_table("asset_slots")
    op.drop_table("product_visual_plans")
    op.rename_table("platform_rules", "platform_rules_normalized")
    op.create_table(
        "platform_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("platform", sa.Enum(name="platformcode", create_type=False), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("image_slot", sa.Enum(name="imageslot", create_type=False), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
    )
    op.execute("""INSERT INTO platform_rules (id,platform,market,category,image_slot,rule_version,effective_date,constraints,enabled,created_at,updated_at)
      SELECT rv.id,upper(p.code)::platformcode,pm.code,pc.code,r.image_slot::imageslot,rv.version,rv.effective_date,rv.extra_constraints,rv.enabled,rv.created_at,rv.updated_at FROM rule_versions rv JOIN platform_rules_normalized r ON r.id=rv.platform_rule_id JOIN platform_categories pc ON pc.id=r.category_id JOIN platform_markets pm ON pm.id=pc.market_id JOIN platforms p ON p.id=pm.platform_id""")
    op.drop_constraint(
        "generation_jobs_resolved_rule_id_fkey", "generation_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "generation_jobs_resolved_rule_id_fkey",
        "generation_jobs",
        "platform_rules",
        ["resolved_rule_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_table("rule_versions")
    op.drop_table("platform_rules_normalized")
    op.drop_table("platform_categories")
    op.drop_table("platform_markets")
    op.drop_table("platforms")
