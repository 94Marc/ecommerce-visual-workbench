"""Add deterministic scene-placement review reasons."""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_scene_placement_review_reasons"
down_revision: str | None = "0008_detail_content_semantics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE rejectreason ADD VALUE IF NOT EXISTS "
        "'PRODUCT_PLACEMENT_UNREALISTIC'"
    )
    op.execute(
        "ALTER TYPE rejectreason ADD VALUE IF NOT EXISTS "
        "'PERSPECTIVE_UNREALISTIC'"
    )
    op.execute(
        "ALTER TYPE rejectreason ADD VALUE IF NOT EXISTS "
        "'SHADOW_UNREALISTIC'"
    )


def downgrade() -> None:
    # PostgreSQL enum values cannot be safely removed while historical reviews
    # may reference them. Keep the values to preserve review traceability.
    pass
