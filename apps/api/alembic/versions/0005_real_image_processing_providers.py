"""Add real image processing providers and workflow registry."""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_real_image_processing_providers"
down_revision: str | None = "0004_fidelity_and_quality_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

task_type = sa.Enum(
    "REMOVE_BACKGROUND",
    "UPSCALE",
    "GENERATE_SCENE",
    "GENERATE_USAGE",
    "GENERATE_BACKGROUND",
    "GENERATE_DETAIL",
    "GENERATE_MAIN",
    name="tasktype",
)

WORKFLOWS = (
    (
        "10000000-0000-4000-8000-000000000001",
        "product_scene",
        "GENERATE_SCENE",
        "product_scene.v1.json",
        {"generation_mode": "BALANCED", "steps": 28, "cfg": 5.5, "denoise": 0.58, "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_scene"},
    ),
    (
        "10000000-0000-4000-8000-000000000002",
        "product_usage",
        "GENERATE_USAGE",
        "product_usage.v1.json",
        {"generation_mode": "BALANCED", "steps": 28, "cfg": 5.5, "denoise": 0.52, "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_usage"},
    ),
    (
        "10000000-0000-4000-8000-000000000003",
        "product_background",
        "GENERATE_BACKGROUND",
        "product_background.v1.json",
        {"generation_mode": "CREATIVE", "steps": 30, "cfg": 6.0, "denoise": 0.68, "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_background"},
    ),
    (
        "10000000-0000-4000-8000-000000000004",
        "product_detail",
        "GENERATE_DETAIL",
        "product_detail.v1.json",
        {"generation_mode": "STRICT", "steps": 24, "cfg": 4.5, "denoise": 0.28, "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_detail"},
    ),
    (
        "10000000-0000-4000-8000-000000000005",
        "product_main_white",
        "GENERATE_MAIN",
        "product_main_white.v1.json",
        {"generation_mode": "STRICT", "steps": 24, "cfg": 4.0, "denoise": 0.22, "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_main_white"},
    ),
)


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("task_type", task_type, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("workflow_file", sa.String(500), nullable=False),
        sa.Column("default_parameters", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "version"),
    )
    op.create_index("ix_workflow_definitions_name", "workflow_definitions", ["name"])
    op.create_index("ix_workflow_definitions_task_type", "workflow_definitions", ["task_type"])
    op.create_index("ix_workflow_definitions_provider", "workflow_definitions", ["provider"])
    op.create_index("ix_workflow_definitions_active", "workflow_definitions", ["active"])

    for workflow_id, name, workflow_task, workflow_file, parameters in WORKFLOWS:
        payload = json.dumps(parameters, separators=(",", ":")).replace("'", "''")
        op.execute(
            "INSERT INTO workflow_definitions "
            "(id,name,version,task_type,provider,workflow_file,default_parameters,"
            "active,created_at,updated_at) VALUES "
            f"('{workflow_id}'::uuid,'{name}','1.0.0','{workflow_task}',"
            f"'comfyui','{workflow_file}','{payload}'::json,true,now(),now())"
        )

    op.add_column(
        "generation_jobs",
        sa.Column("task_type", task_type, nullable=False, server_default="GENERATE_MAIN"),
    )
    op.add_column(
        "generation_jobs",
        sa.Column(
            "workflow_definition_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_definitions.id", ondelete="RESTRICT"),
        ),
    )
    op.add_column("generation_jobs", sa.Column("negative_prompt", sa.Text()))
    op.add_column("generation_jobs", sa.Column("seed", sa.BigInteger()))
    op.add_column(
        "generation_jobs",
        sa.Column(
            "output_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("generation_jobs", "resolved_rule_id", nullable=True)
    op.alter_column("generation_jobs", "platform", nullable=True)
    op.alter_column("generation_jobs", "market", nullable=True)
    op.alter_column("generation_jobs", "category", nullable=True)
    op.alter_column("generation_jobs", "image_slot", nullable=True)
    op.create_index("ix_generation_jobs_task_type", "generation_jobs", ["task_type"])
    op.create_index(
        "ix_generation_jobs_workflow_definition_id",
        "generation_jobs",
        ["workflow_definition_id"],
    )
    op.execute("UPDATE generation_jobs SET task_type='GENERATE_SCENE' WHERE image_slot::text='SCENE'")
    op.execute("UPDATE generation_jobs SET task_type='GENERATE_USAGE' WHERE image_slot::text='USAGE'")
    op.execute("UPDATE generation_jobs SET task_type='GENERATE_DETAIL' WHERE image_slot::text IN ('DETAIL','DIMENSION','PACKAGE','CLOSEUP')")
    op.execute("UPDATE generation_jobs SET task_type='GENERATE_BACKGROUND' WHERE image_slot::text='COMPARE'")


def downgrade() -> None:
    op.alter_column("generation_jobs", "image_slot", nullable=False)
    op.alter_column("generation_jobs", "category", nullable=False)
    op.alter_column("generation_jobs", "market", nullable=False)
    op.alter_column("generation_jobs", "platform", nullable=False)
    op.alter_column("generation_jobs", "resolved_rule_id", nullable=False)
    op.drop_index("ix_generation_jobs_workflow_definition_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_task_type", table_name="generation_jobs")
    op.drop_column("generation_jobs", "output_metadata")
    op.drop_column("generation_jobs", "seed")
    op.drop_column("generation_jobs", "negative_prompt")
    op.drop_column("generation_jobs", "workflow_definition_id")
    op.drop_column("generation_jobs", "task_type")
    op.drop_table("workflow_definitions")
    task_type.drop(op.get_bind(), checkfirst=True)
