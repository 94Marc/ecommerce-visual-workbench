from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.jobs.models import GenerationJob, ValidationStatus

Point = tuple[float, float]
Polygon = tuple[Point, ...]


class SceneAnchor(StrEnum):
    COUNTERTOP = "COUNTERTOP"
    TABLE = "TABLE"
    SINK_EDGE = "SINK_EDGE"
    HANGING = "HANGING"
    FLOOR = "FLOOR"
    CUSTOM = "CUSTOM"


class PhysicalScaleMode(StrEnum):
    VISUAL_ESTIMATE = "VISUAL_ESTIMATE"
    KNOWN_DIMENSION = "KNOWN_DIMENSION"


class PlacementValidationCode(StrEnum):
    VALID = "VALID"
    PLACEMENT_INVALID = "PLACEMENT_INVALID"
    PLACEMENT_OVERFLOW = "PLACEMENT_OVERFLOW"
    PERSPECTIVE_INVALID = "PERSPECTIVE_INVALID"
    SHADOW_INVALID = "SHADOW_INVALID"


class PlacementWarningCode(StrEnum):
    PLACEMENT_SCALE_WARNING = "PLACEMENT_SCALE_WARNING"


@dataclass(frozen=True)
class AnchorRegion:
    anchor_x: float
    anchor_y: float
    anchor_width: float
    anchor_height: float
    surface_angle: float = 0.0
    anchor_polygon: Polygon | None = None

    def polygon(self) -> Polygon:
        if self.anchor_polygon:
            return self.anchor_polygon
        return (
            (self.anchor_x, self.anchor_y),
            (self.anchor_x + self.anchor_width, self.anchor_y),
            (
                self.anchor_x + self.anchor_width,
                self.anchor_y + self.anchor_height,
            ),
            (self.anchor_x, self.anchor_y + self.anchor_height),
        )


@dataclass(frozen=True)
class ShadowParameters:
    offset_x: float
    offset_y: float
    blur: float
    opacity: float
    compression: float = 1.0
    derived_from_transformed_alpha: bool = True


@dataclass(frozen=True)
class ScenePlacementRequest:
    anchor_type: SceneAnchor
    anchor_region: AnchorRegion
    subject_polygon: Polygon
    transform_matrix: tuple[tuple[float, float, float], ...]
    shadow: ShadowParameters
    physical_scale_mode: PhysicalScaleMode = PhysicalScaleMode.VISUAL_ESTIMATE


@dataclass(frozen=True)
class ScenePlacementValidationResult:
    status: PlacementValidationCode
    failure_codes: tuple[PlacementValidationCode, ...]
    warning_codes: tuple[PlacementWarningCode, ...]
    subject_inside_anchor_ratio: float
    subject_overflow_ratio: float
    subject_area_ratio: float
    perspective_checks: dict[str, bool | float]
    shadow_checks: dict[str, bool | float]

    @property
    def is_valid(self) -> bool:
        return not self.failure_codes

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "failure_codes": [code.value for code in self.failure_codes],
            "warning_codes": [code.value for code in self.warning_codes],
            "subject_inside_anchor_ratio": self.subject_inside_anchor_ratio,
            "subject_overflow_ratio": self.subject_overflow_ratio,
            "subject_area_ratio": self.subject_area_ratio,
            "perspective_checks": self.perspective_checks,
            "shadow_checks": self.shadow_checks,
        }


class ScenePlacementValidator:
    COUNTERTOP_MIN_INSIDE_RATIO = 0.95
    COUNTERTOP_MAX_OVERFLOW_RATIO = 0.05
    COUNTERTOP_MIN_AREA_RATIO = 0.05
    COUNTERTOP_MAX_AREA_RATIO = 0.18
    COUNTERTOP_MAX_SHADOW_OFFSET = 0.03
    COUNTERTOP_MAX_SHADOW_BLUR = 0.04
    COUNTERTOP_MAX_SHADOW_OPACITY = 0.35
    MAX_SURFACE_ANGLE_DELTA = 15.0
    MAX_EDGE_SCALE_RATIO = 25.0
    MAX_TRANSFORM_CONDITION = 100_000_000.0

    def validate(self, request: ScenePlacementRequest) -> ScenePlacementValidationResult:
        anchor_polygon = request.anchor_region.polygon()
        self._validate_normalized_polygon(anchor_polygon, "anchor_polygon")
        self._validate_normalized_polygon(request.subject_polygon, "subject_polygon")

        subject_area = abs(_signed_area(request.subject_polygon))
        intersection = _convex_intersection(request.subject_polygon, anchor_polygon)
        intersection_area = abs(_signed_area(intersection)) if len(intersection) >= 3 else 0.0
        inside_ratio = min(1.0, intersection_area / subject_area) if subject_area else 0.0
        overflow_ratio = max(0.0, 1.0 - inside_ratio)
        area_ratio = subject_area

        perspective_checks = self._check_perspective(request)
        shadow_checks = self._check_shadow(request)
        failures: list[PlacementValidationCode] = []
        warnings: list[PlacementWarningCode] = []

        if not all(
            bool(perspective_checks[key])
            for key in (
                "convex",
                "not_flipped",
                "scale_is_reasonable",
                "matrix_is_valid",
                "surface_alignment_valid",
            )
        ):
            failures.append(PlacementValidationCode.PERSPECTIVE_INVALID)

        if request.anchor_type is SceneAnchor.COUNTERTOP:
            if inside_ratio < self.COUNTERTOP_MIN_INSIDE_RATIO:
                failures.append(PlacementValidationCode.PLACEMENT_INVALID)
            if overflow_ratio > self.COUNTERTOP_MAX_OVERFLOW_RATIO:
                failures.append(PlacementValidationCode.PLACEMENT_OVERFLOW)
            if not (
                self.COUNTERTOP_MIN_AREA_RATIO
                <= area_ratio
                <= self.COUNTERTOP_MAX_AREA_RATIO
            ):
                warnings.append(PlacementWarningCode.PLACEMENT_SCALE_WARNING)
            if not all(
                bool(shadow_checks[key])
                for key in (
                    "derived_from_transformed_alpha",
                    "offset_is_small",
                    "blur_is_conservative",
                    "opacity_is_conservative",
                    "compression_is_valid",
                )
            ):
                failures.append(PlacementValidationCode.SHADOW_INVALID)

        status = failures[0] if failures else PlacementValidationCode.VALID
        return ScenePlacementValidationResult(
            status=status,
            failure_codes=tuple(failures),
            warning_codes=tuple(warnings),
            subject_inside_anchor_ratio=round(inside_ratio, 6),
            subject_overflow_ratio=round(overflow_ratio, 6),
            subject_area_ratio=round(area_ratio, 6),
            perspective_checks=perspective_checks,
            shadow_checks=shadow_checks,
        )

    @staticmethod
    def _validate_normalized_polygon(polygon: Polygon, field: str) -> None:
        if len(polygon) < 3:
            raise ValueError(f"{field} must contain at least three points")
        if any(not (0.0 <= coordinate <= 1.0) for point in polygon for coordinate in point):
            raise ValueError(f"{field} coordinates must be normalized to 0-1")
        if abs(_signed_area(polygon)) <= 1e-9:
            raise ValueError(f"{field} must have non-zero area")

    def _check_perspective(
        self, request: ScenePlacementRequest
    ) -> dict[str, bool | float]:
        polygon = request.subject_polygon
        convex = _is_convex(polygon)
        signed_area = _signed_area(polygon)
        not_flipped = signed_area > 0
        edge_lengths = [
            math.dist(polygon[index], polygon[(index + 1) % len(polygon)])
            for index in range(len(polygon))
        ]
        minimum_edge = min(edge_lengths)
        maximum_edge = max(edge_lengths)
        edge_scale_ratio = maximum_edge / minimum_edge if minimum_edge > 0 else math.inf
        scale_is_reasonable = (
            minimum_edge >= 0.005 and edge_scale_ratio <= self.MAX_EDGE_SCALE_RATIO
        )

        matrix = request.transform_matrix
        matrix_is_valid = False
        matrix_determinant = 0.0
        matrix_condition = math.inf
        if len(matrix) == 3 and all(len(row) == 3 for row in matrix):
            matrix_determinant = _determinant_3x3(matrix)
            matrix_condition = _condition_estimate(matrix)
            matrix_is_valid = (
                all(math.isfinite(value) for row in matrix for value in row)
                and abs(matrix_determinant) > 1e-10
                and matrix_condition <= self.MAX_TRANSFORM_CONDITION
            )

        top_edge_angle = math.degrees(
            math.atan2(
                polygon[1][1] - polygon[0][1],
                polygon[1][0] - polygon[0][0],
            )
        )
        surface_angle_delta = _smallest_angle_delta(
            top_edge_angle, request.anchor_region.surface_angle
        )
        surface_alignment_valid = surface_angle_delta <= self.MAX_SURFACE_ANGLE_DELTA
        return {
            "convex": convex,
            "not_flipped": not_flipped,
            "scale_is_reasonable": scale_is_reasonable,
            "edge_scale_ratio": round(edge_scale_ratio, 6),
            "matrix_is_valid": matrix_is_valid,
            "matrix_determinant": round(matrix_determinant, 10),
            "matrix_condition_estimate": round(matrix_condition, 6),
            "top_edge_angle": round(top_edge_angle, 6),
            "surface_angle": request.anchor_region.surface_angle,
            "surface_angle_delta": round(surface_angle_delta, 6),
            "surface_alignment_valid": surface_alignment_valid,
        }

    def _check_shadow(self, request: ScenePlacementRequest) -> dict[str, bool | float]:
        shadow = request.shadow
        offset = math.hypot(shadow.offset_x, shadow.offset_y)
        return {
            "derived_from_transformed_alpha": shadow.derived_from_transformed_alpha,
            "shadow_offset": round(offset, 6),
            "shadow_blur": shadow.blur,
            "shadow_opacity": shadow.opacity,
            "shadow_compression": shadow.compression,
            "offset_is_small": offset <= self.COUNTERTOP_MAX_SHADOW_OFFSET,
            "blur_is_conservative": 0.0 <= shadow.blur <= self.COUNTERTOP_MAX_SHADOW_BLUR,
            "opacity_is_conservative": (
                0.0 <= shadow.opacity <= self.COUNTERTOP_MAX_SHADOW_OPACITY
            ),
            "compression_is_valid": 0.0 < shadow.compression <= 1.0,
        }


class ScenePlacementValidationService:
    def __init__(
        self,
        session: Session,
        validator: ScenePlacementValidator | None = None,
    ) -> None:
        self.session = session
        self.validator = validator or ScenePlacementValidator()

    def validate_and_persist(
        self,
        job_id: uuid.UUID,
        request: ScenePlacementRequest,
        *,
        anchor_name: str,
        default_auto_placement: bool,
        measurement_source: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> ScenePlacementValidationResult:
        job = self.session.get(GenerationJob, job_id)
        if job is None:
            raise LookupError(f"generation job {job_id} not found")
        result = self.validator.validate(request)
        region = request.anchor_region
        validation_data: dict[str, Any] = {
            **result.as_dict(),
            "anchor_name": anchor_name,
            "anchor_type": request.anchor_type.value,
            "anchor_polygon": [list(point) for point in region.polygon()],
            "anchor_x": region.anchor_x,
            "anchor_y": region.anchor_y,
            "anchor_width": region.anchor_width,
            "anchor_height": region.anchor_height,
            "surface_angle": region.surface_angle,
            "physical_scale_mode": request.physical_scale_mode.value,
            "measurement_source": measurement_source,
            "transform_matrix": [list(row) for row in request.transform_matrix],
            "shadow_offset": [request.shadow.offset_x, request.shadow.offset_y],
            "shadow_blur": request.shadow.blur,
            "shadow_opacity": request.shadow.opacity,
            "default_auto_placement": default_auto_placement,
            **(extra_metadata or {}),
        }
        job.validation_status = (
            ValidationStatus.PASSED if result.is_valid else ValidationStatus.FAILED
        )
        job.validation_result = validation_data
        job.output_metadata = {
            **job.output_metadata,
            "anchor_name": anchor_name,
            "anchor_type": request.anchor_type.value,
            "anchor_polygon": validation_data["anchor_polygon"],
            "anchor_region": {
                "anchor_x": region.anchor_x,
                "anchor_y": region.anchor_y,
                "anchor_width": region.anchor_width,
                "anchor_height": region.anchor_height,
                "surface_angle": region.surface_angle,
            },
            "default_auto_placement": default_auto_placement,
            "scene_placement_validation": validation_data,
        }
        self.session.commit()
        self.session.refresh(job)
        return result


def _signed_area(polygon: Sequence[Point]) -> float:
    if len(polygon) < 3:
        return 0.0
    return 0.5 * sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    )


def _is_convex(polygon: Polygon) -> bool:
    signs: list[bool] = []
    for index in range(len(polygon)):
        first = polygon[index]
        second = polygon[(index + 1) % len(polygon)]
        third = polygon[(index + 2) % len(polygon)]
        cross = _cross(first, second, third)
        if abs(cross) > 1e-9:
            signs.append(cross > 0)
    return bool(signs) and all(sign == signs[0] for sign in signs)


def _convex_intersection(subject: Polygon, clip: Polygon) -> Polygon:
    output: list[Point] = list(subject)
    clip_orientation = 1.0 if _signed_area(clip) > 0 else -1.0
    for index in range(len(clip)):
        edge_start = clip[index]
        edge_end = clip[(index + 1) % len(clip)]
        input_points = output
        output = []
        if not input_points:
            break
        previous = input_points[-1]
        for current in input_points:
            current_inside = (
                clip_orientation * _cross(edge_start, edge_end, current) >= -1e-9
            )
            previous_inside = (
                clip_orientation * _cross(edge_start, edge_end, previous) >= -1e-9
            )
            if current_inside:
                if not previous_inside:
                    output.append(_line_intersection(previous, current, edge_start, edge_end))
                output.append(current)
            elif previous_inside:
                output.append(_line_intersection(previous, current, edge_start, edge_end))
            previous = current
    return tuple(output)


def _cross(origin: Point, first: Point, second: Point) -> float:
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (
        first[1] - origin[1]
    ) * (second[0] - origin[0])


def _line_intersection(
    first_start: Point, first_end: Point, second_start: Point, second_end: Point
) -> Point:
    first_x = first_end[0] - first_start[0]
    first_y = first_end[1] - first_start[1]
    second_x = second_end[0] - second_start[0]
    second_y = second_end[1] - second_start[1]
    denominator = first_x * second_y - first_y * second_x
    if abs(denominator) <= 1e-12:
        return first_end
    delta_x = second_start[0] - first_start[0]
    delta_y = second_start[1] - first_start[1]
    factor = (delta_x * second_y - delta_y * second_x) / denominator
    return first_start[0] + factor * first_x, first_start[1] + factor * first_y


def _determinant_3x3(matrix: tuple[tuple[float, float, float], ...]) -> float:
    return (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )


def _condition_estimate(matrix: tuple[tuple[float, float, float], ...]) -> float:
    determinant = _determinant_3x3(matrix)
    if abs(determinant) <= 1e-12:
        return math.inf
    inverse = (
        (
            (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1]) / determinant,
            (matrix[0][2] * matrix[2][1] - matrix[0][1] * matrix[2][2]) / determinant,
            (matrix[0][1] * matrix[1][2] - matrix[0][2] * matrix[1][1]) / determinant,
        ),
        (
            (matrix[1][2] * matrix[2][0] - matrix[1][0] * matrix[2][2]) / determinant,
            (matrix[0][0] * matrix[2][2] - matrix[0][2] * matrix[2][0]) / determinant,
            (matrix[0][2] * matrix[1][0] - matrix[0][0] * matrix[1][2]) / determinant,
        ),
        (
            (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0]) / determinant,
            (matrix[0][1] * matrix[2][0] - matrix[0][0] * matrix[2][1]) / determinant,
            (matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]) / determinant,
        ),
    )
    norm = max(sum(abs(value) for value in row) for row in matrix)
    inverse_norm = max(sum(abs(value) for value in row) for row in inverse)
    return norm * inverse_norm


def _smallest_angle_delta(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)
