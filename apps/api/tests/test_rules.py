import json
from datetime import date
from pathlib import Path

import pytest
from app.rules.models import ImageSlot, PlatformCode
from app.rules.schemas import ImageProbe, PlatformRuleCreate
from app.rules.service import RuleNotFoundError, RuleService


def rule(version: str, effective: date, **overrides) -> PlatformRuleCreate:
    values = {
        "platform": PlatformCode.TEMU,
        "market": "US",
        "category": "kitchen",
        "image_slot": ImageSlot.MAIN,
        "rule_version": version,
        "effective_date": effective,
        "constraints": {"min_width": 1000, "aspect_ratios": ["1:1"]},
    }
    values.update(overrides)
    return PlatformRuleCreate(**values)


def test_resolves_latest_effective_rule(session):
    rules = RuleService(session)
    old = rules.create_rule(rule("1.0.0", date(2026, 1, 1)))
    current = rules.create_rule(rule("1.1.0", date(2026, 6, 1)))
    rules.create_rule(rule("2.0.0", date(2027, 1, 1)))

    assert (
        rules.resolve(PlatformCode.TEMU, "US", "kitchen", ImageSlot.MAIN, date(2026, 8, 10)).id
        == current.id
    )
    assert (
        rules.resolve(PlatformCode.TEMU, "US", "kitchen", ImageSlot.MAIN, date(2026, 2, 1)).id
        == old.id
    )


def test_rule_validation_returns_specific_violations(session):
    rules = RuleService(session)
    temu = rules.create_rule(rule("1.0.0", date(2026, 1, 1)))
    result = rules.validate_image(
        temu, ImageProbe(width=800, height=1000, mime_type="image/jpeg", byte_size=100)
    )
    assert result.valid is False
    assert "width must be at least 1000px" in result.violations
    assert any("aspect ratio" in violation for violation in result.violations)


def test_no_future_rule_is_resolved(session):
    rules = RuleService(session)
    rules.create_rule(rule("2.0.0", date(2027, 1, 1)))
    with pytest.raises(RuleNotFoundError):
        rules.resolve(PlatformCode.TEMU, "US", "kitchen", ImageSlot.MAIN, date(2026, 8, 10))


def test_semantic_rule_version_breaks_same_day_ties(session):
    rules = RuleService(session)
    rules.create_rule(rule("2.0.0", date(2026, 1, 1)))
    latest = rules.create_rule(rule("10.0.0", date(2026, 1, 1)))

    resolved = rules.resolve(PlatformCode.TEMU, "US", "kitchen", ImageSlot.MAIN, date(2026, 8, 10))

    assert resolved.id == latest.id


def test_rule_creation_builds_platform_hierarchy(session):
    rules = RuleService(session)
    created = rules.create_rule(rule("1.0.0", date(2026, 1, 1)))
    assert (created.platform, created.market, created.category) == ("temu", "US", "kitchen")
    assert [item.code for item in rules.list_platforms()] == ["temu"]
    assert [item.code for item in rules.list_markets()] == ["US"]
    assert [item.code for item in rules.list_categories()] == ["kitchen"]


def test_rule_validation_honors_text_and_watermark_policies(session):
    rules = RuleService(session)
    created = rules.create_rule(
        rule("1.0.0", date(2026, 1, 1), text_allowed=False, watermark_allowed=False)
    )
    result = rules.validate_image(
        created,
        ImageProbe(
            width=1000,
            height=1000,
            mime_type="image/jpeg",
            byte_size=100,
            has_text=True,
            has_watermark=True,
        ),
    )
    assert result.violations == ["text is not allowed", "watermark is not allowed"]


def test_platform_rule_api_returns_flattened_version(client):
    response = client.post(
        "/api/v1/platform-rules",
        json={
            "platform": "amazon",
            "market": "US",
            "category": "home",
            "image_slot": "MAIN",
            "image_type": "MAIN",
            "version": "1.2.0",
            "effective_date": "2026-08-10",
            "min_width": 2000,
            "min_height": 2000,
            "ratio": "1:1",
            "max_size": 10485760,
            "text_allowed": False,
            "watermark_allowed": False,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert (payload["platform"], payload["market"], payload["category"]) == (
        "amazon",
        "US",
        "home",
    )
    assert payload["version"] == "1.2.0"
    assert client.get("/api/v1/platform-rules?platform=amazon").json()[0]["id"] == payload["id"]


def test_all_platforms_have_registered_seed_frameworks():
    root = Path(__file__).parents[3]
    registry = json.loads((root / "platforms" / "registry.json").read_text(encoding="utf-8"))
    codes = {entry["code"] for entry in registry["platforms"]}
    assert codes == {member.value for member in PlatformCode}
    for entry in registry["platforms"]:
        folder = entry["code"].replace("_", "-")
        assert (root / "platforms" / folder / "default_rules.json").is_file()
