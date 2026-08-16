"""Add detail content semantics and non-production data guards."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_detail_content_semantics"
down_revision: str | None = "0007_smoke_test_asset_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

content_kind = sa.Enum(
    "SELLING_POINT",
    "PARAMETER",
    "FEATURE",
    "MATERIAL",
    "CLOSEUP",
    "COMPARE",
    "PACKAGE_INFO",
    name="contentkind",
)


def upgrade() -> None:
    content_kind.create(op.get_bind(), checkfirst=True)
    op.add_column("assets", sa.Column("content_kind", content_kind, nullable=True))
    op.create_index("ix_assets_content_kind", "assets", ["content_kind"])
    op.add_column(
        "asset_versions",
        sa.Column(
            "contains_demo_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "asset_versions",
        sa.Column(
            "demo_data_fields",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.create_index(
        "ix_asset_versions_contains_demo_data",
        "asset_versions",
        ["contains_demo_data"],
    )

    op.execute(
        """
        UPDATE assets AS asset
        SET
            asset_type = 'DETAIL',
            content_kind = CASE template.template_type::text
                WHEN 'SELLING_POINT' THEN 'SELLING_POINT'::contentkind
                WHEN 'PARAMETER' THEN 'PARAMETER'::contentkind
            END
        FROM asset_versions AS version
        JOIN template_render_records AS render
          ON render.output_asset_version_id = version.id
        JOIN templates AS template
          ON template.id = render.template_id
        WHERE version.asset_id = asset.id
          AND template.template_type::text IN ('SELLING_POINT', 'PARAMETER')
        """
    )
    op.execute(
        """
        UPDATE asset_versions AS version
        SET
            contains_demo_data = true,
            demo_data_fields = COALESCE(
                job.output_metadata->'demo_data_fields',
                '["legacy.data_source"]'::json
            )
        FROM generation_jobs AS job
        WHERE job.output_version_id = version.id
          AND upper(COALESCE(job.output_metadata->>'data_source', '')) IN (
              'DEMO_TEST_DATA', 'PLACEHOLDER', 'UNKNOWN', 'MISSING_SOURCE'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE assets SET asset_type='COMPARE' "
        "WHERE content_kind='SELLING_POINT'"
    )
    op.drop_index(
        "ix_asset_versions_contains_demo_data",
        table_name="asset_versions",
    )
    op.drop_column("asset_versions", "demo_data_fields")
    op.drop_column("asset_versions", "contains_demo_data")
    op.drop_index("ix_assets_content_kind", table_name="assets")
    op.drop_column("assets", "content_kind")
    content_kind.drop(op.get_bind(), checkfirst=True)
