import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.models import TaskType, WorkflowDefinition

DEFAULT_WORKFLOWS: tuple[dict[str, Any], ...] = (
    {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000001"),
        "name": "product_scene",
        "version": "1.0.0",
        "task_type": TaskType.GENERATE_SCENE,
        "provider": "comfyui",
        "workflow_file": "product_scene.v1.json",
        "default_parameters": {
            "generation_mode": "BALANCED", "steps": 28, "cfg": 5.5, "denoise": 0.58,
            "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_scene",
        },
    },
    {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000002"),
        "name": "product_usage",
        "version": "1.0.0",
        "task_type": TaskType.GENERATE_USAGE,
        "provider": "comfyui",
        "workflow_file": "product_usage.v1.json",
        "default_parameters": {
            "generation_mode": "BALANCED", "steps": 28, "cfg": 5.5, "denoise": 0.52,
            "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_usage",
        },
    },
    {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000003"),
        "name": "product_background",
        "version": "1.0.0",
        "task_type": TaskType.GENERATE_BACKGROUND,
        "provider": "comfyui",
        "workflow_file": "product_background.v1.json",
        "default_parameters": {
            "generation_mode": "CREATIVE", "steps": 30, "cfg": 6.0, "denoise": 0.68,
            "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_background",
        },
    },
    {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000004"),
        "name": "product_detail",
        "version": "1.0.0",
        "task_type": TaskType.GENERATE_DETAIL,
        "provider": "comfyui",
        "workflow_file": "product_detail.v1.json",
        "default_parameters": {
            "generation_mode": "STRICT", "steps": 24, "cfg": 4.5, "denoise": 0.28,
            "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_detail",
        },
    },
    {
        "id": uuid.UUID("10000000-0000-4000-8000-000000000005"),
        "name": "product_main_white",
        "version": "1.0.0",
        "task_type": TaskType.GENERATE_MAIN,
        "provider": "comfyui",
        "workflow_file": "product_main_white.v1.json",
        "default_parameters": {
            "generation_mode": "STRICT", "steps": 24, "cfg": 4.0, "denoise": 0.22,
            "checkpoint": "sd_xl_base_1.0.safetensors", "filename_prefix": "product_main_white",
        },
    },
)


class WorkflowNotFoundError(LookupError):
    pass


class WorkflowRegistry:
    def __init__(self, session: Session):
        self.session = session

    def ensure_defaults(self) -> None:
        existing = set(self.session.scalars(select(WorkflowDefinition.id)))
        changed = False
        for definition in DEFAULT_WORKFLOWS:
            if definition["id"] not in existing:
                self.session.add(WorkflowDefinition(**definition))
                changed = True
        if changed:
            self.session.commit()

    def list(self, active_only: bool = True) -> list[WorkflowDefinition]:
        self.ensure_defaults()
        statement = select(WorkflowDefinition)
        if active_only:
            statement = statement.where(WorkflowDefinition.active.is_(True))
        return list(
            self.session.scalars(
                statement.order_by(WorkflowDefinition.name, WorkflowDefinition.version.desc())
            )
        )

    def get(self, workflow_id: uuid.UUID) -> WorkflowDefinition:
        self.ensure_defaults()
        workflow = self.session.get(WorkflowDefinition, workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(f"workflow {workflow_id} not found")
        return workflow

    def resolve(
        self, task_type: TaskType, workflow_id: uuid.UUID | None = None
    ) -> WorkflowDefinition:
        self.ensure_defaults()
        if workflow_id is not None:
            workflow = self.get(workflow_id)
            if workflow.task_type is not task_type:
                raise WorkflowNotFoundError("workflow does not support the selected task type")
            if not workflow.active:
                raise WorkflowNotFoundError("workflow is inactive")
            return workflow
        workflow = self.session.scalar(
            select(WorkflowDefinition)
            .where(
                WorkflowDefinition.task_type == task_type,
                WorkflowDefinition.active.is_(True),
            )
            .order_by(WorkflowDefinition.version.desc())
        )
        if workflow is None:
            raise WorkflowNotFoundError(f"no active workflow for {task_type.value}")
        return workflow
