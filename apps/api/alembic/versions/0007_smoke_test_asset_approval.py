"""Keep smoke-test approval distinct from production asset approval."""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_smoke_test_asset_approval"
down_revision: str | None = "0006_ecommerce_template_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE assetstatus ADD VALUE IF NOT EXISTS "
        "'APPROVED_FOR_SMOKE_TEST' BEFORE 'APPROVED'"
    )
    op.execute(
        "ALTER TYPE reviewdecision ADD VALUE IF NOT EXISTS "
        "'APPROVED_FOR_SMOKE_TEST' BEFORE 'APPROVED'"
    )


def downgrade() -> None:
    # PostgreSQL enum values cannot be safely removed while preserving dependent data.
    pass
