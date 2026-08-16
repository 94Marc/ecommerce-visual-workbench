import uuid
from types import SimpleNamespace

import pytest
from app.jobs.scene_placement import (
    AnchorRegion,
    PhysicalScaleMode,
    PlacementValidationCode,
    PlacementWarningCode,
    SceneAnchor,
    ScenePlacementRequest,
    ScenePlacementValidationService,
    ScenePlacementValidator,
    ShadowParameters,
)


def request_for(
    *,
    subject_polygon,
    anchor_polygon,
    surface_angle=0.0,
    transform_matrix=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    shadow=None,
):
    xs = [point[0] for point in anchor_polygon]
    ys = [point[1] for point in anchor_polygon]
    return ScenePlacementRequest(
        anchor_type=SceneAnchor.COUNTERTOP,
        anchor_region=AnchorRegion(
            anchor_x=min(xs),
            anchor_y=min(ys),
            anchor_width=max(xs) - min(xs),
            anchor_height=max(ys) - min(ys),
            surface_angle=surface_angle,
            anchor_polygon=anchor_polygon,
        ),
        subject_polygon=subject_polygon,
        transform_matrix=transform_matrix,
        shadow=shadow
        or ShadowParameters(
            offset_x=0.0,
            offset_y=0.004,
            blur=0.006,
            opacity=0.13,
            compression=0.62,
        ),
        physical_scale_mode=PhysicalScaleMode.VISUAL_ESTIMATE,
    )


def test_countertop_main_candidate_is_inside_anchor_with_scale_warning():
    result = ScenePlacementValidator().validate(
        request_for(
            subject_polygon=(
                (330 / 768, 481 / 768),
                (500 / 768, 481 / 768),
                (515 / 768, 521 / 768),
                (315 / 768, 521 / 768),
            ),
            anchor_polygon=((0.39, 0.62), (0.70, 0.62), (0.70, 0.683), (0.39, 0.683)),
            transform_matrix=(
                (0.5431309904, -0.1963722397, 330.0),
                (0.0, -0.1203470032, 481.0),
                (0.0, -0.0004731861, 1.0),
            ),
        )
    )

    assert result.is_valid is True
    assert result.status is PlacementValidationCode.VALID
    assert result.subject_inside_anchor_ratio == pytest.approx(1.0)
    assert result.subject_overflow_ratio == pytest.approx(0.0)
    assert result.subject_area_ratio < 0.05
    assert result.warning_codes == (PlacementWarningCode.PLACEMENT_SCALE_WARNING,)


def test_right_edge_candidate_is_blocked_when_it_overflows_support_surface():
    result = ScenePlacementValidator().validate(
        request_for(
            subject_polygon=(
                (575 / 768, 545 / 768),
                (716 / 768, 570 / 768),
                (760 / 768, 635 / 768),
                (604 / 768, 603 / 768),
            ),
            anchor_polygon=(
                (0.70, 0.645),
                (1.0, 0.69),
                (1.0, 0.78),
                (0.78, 0.72),
            ),
            surface_angle=9.0,
            transform_matrix=(
                (0.2901523389, -0.0540598343, 575.0),
                (-0.0477623343, 0.0376637799, 545.0),
                (-0.0002239202, -0.0002409644, 1.0),
            ),
        )
    )

    assert result.status is PlacementValidationCode.PLACEMENT_INVALID
    assert PlacementValidationCode.PLACEMENT_INVALID in result.failure_codes
    assert PlacementValidationCode.PLACEMENT_OVERFLOW in result.failure_codes
    assert result.subject_inside_anchor_ratio < 0.95
    assert result.subject_overflow_ratio > 0.05


def test_flipped_subject_polygon_returns_perspective_invalid():
    result = ScenePlacementValidator().validate(
        request_for(
            subject_polygon=((0.2, 0.2), (0.2, 0.5), (0.5, 0.5), (0.5, 0.2)),
            anchor_polygon=((0.1, 0.1), (0.6, 0.1), (0.6, 0.6), (0.1, 0.6)),
        )
    )

    assert result.status is PlacementValidationCode.PERSPECTIVE_INVALID
    assert result.perspective_checks["not_flipped"] is False


def test_countertop_shadow_must_come_from_alpha_and_stay_close_to_surface():
    result = ScenePlacementValidator().validate(
        request_for(
            subject_polygon=((0.2, 0.2), (0.5, 0.2), (0.5, 0.4), (0.2, 0.4)),
            anchor_polygon=((0.1, 0.1), (0.6, 0.1), (0.6, 0.5), (0.1, 0.5)),
            shadow=ShadowParameters(
                offset_x=0.15,
                offset_y=0.15,
                blur=0.08,
                opacity=0.5,
                compression=1.2,
                derived_from_transformed_alpha=False,
            ),
        )
    )

    assert PlacementValidationCode.SHADOW_INVALID in result.failure_codes
    assert result.shadow_checks["derived_from_transformed_alpha"] is False
    assert result.shadow_checks["offset_is_small"] is False


def test_anchor_and_subject_coordinates_must_be_normalized():
    with pytest.raises(ValueError, match="normalized to 0-1"):
        ScenePlacementValidator().validate(
            request_for(
                subject_polygon=((0.2, 0.2), (1.2, 0.2), (0.5, 0.4), (0.2, 0.4)),
                anchor_polygon=((0.1, 0.1), (0.6, 0.1), (0.6, 0.5), (0.1, 0.5)),
            )
        )


def test_validation_service_persists_anchor_metrics_on_generation_job():
    job_id = uuid.uuid4()
    job = SimpleNamespace(
        id=job_id,
        validation_status=None,
        validation_result={},
        output_metadata={"existing_trace": True},
    )

    class RecordingSession:
        committed = False
        refreshed = False

        def get(self, model, requested_id):
            assert requested_id == job_id
            return job

        def commit(self):
            self.committed = True

        def refresh(self, instance):
            assert instance is job
            self.refreshed = True

    session = RecordingSession()
    request = request_for(
        subject_polygon=((0.2, 0.2), (0.5, 0.2), (0.5, 0.4), (0.2, 0.4)),
        anchor_polygon=((0.1, 0.1), (0.6, 0.1), (0.6, 0.5), (0.1, 0.5)),
    )

    result = ScenePlacementValidationService(session).validate_and_persist(
        job_id,
        request,
        anchor_name="COUNTERTOP_MAIN",
        default_auto_placement=True,
        measurement_source="DEMO_TEST_DATA",
        extra_metadata={"architecture_result": "ARCHITECTURE_PASS"},
    )

    assert result.is_valid is True
    assert job.validation_status.value == "passed"
    assert job.validation_result["subject_inside_anchor_ratio"] == 1.0
    assert job.validation_result["subject_overflow_ratio"] == 0.0
    assert job.validation_result["anchor_name"] == "COUNTERTOP_MAIN"
    assert job.validation_result["measurement_source"] == "DEMO_TEST_DATA"
    assert job.output_metadata["existing_trace"] is True
    assert job.output_metadata["scene_placement_validation"] == job.validation_result
    assert session.committed is True
    assert session.refreshed is True
