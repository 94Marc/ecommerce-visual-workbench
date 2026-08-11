from app.core.database import Base


def test_phase_three_schema_contains_all_domain_tables():
    expected = {
        "products",
        "skus",
        "assets",
        "asset_versions",
        "platform_rules",
        "platforms",
        "platform_markets",
        "platform_categories",
        "rule_versions",
        "product_visual_plans",
        "asset_slots",
        "generation_jobs",
        "generation_attempts",
        "generation_quality_checks",
        "workflow_definitions",
        "reviews",
        "export_bundles",
    }
    assert expected == set(Base.metadata.tables)


def test_asset_versions_have_immutable_object_identity_constraints():
    table = Base.metadata.tables["asset_versions"]
    assert table.c.object_key.unique is True
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("asset_id", "version_number") in unique_columns


def test_generation_jobs_pin_source_and_rule_foreign_keys():
    table = Base.metadata.tables["generation_jobs"]
    targets = {foreign_key.target_fullname for foreign_key in table.foreign_keys}
    assert "asset_versions.id" in targets
    assert "rule_versions.id" in targets


def test_visual_plans_pin_product_platform_and_rule_version():
    targets = {
        key.target_fullname for key in Base.metadata.tables["product_visual_plans"].foreign_keys
    }
    assert targets == {"products.id", "platforms.id", "rule_versions.id"}


def test_assets_can_bind_to_one_planned_slot():
    column = Base.metadata.tables["assets"].c.asset_slot_id
    assert {key.target_fullname for key in column.foreign_keys} == {"asset_slots.id"}
    assert column.unique is True


def test_visual_workspace_state_and_soft_delete_columns_exist():
    product_columns = {column.name for column in Base.metadata.tables["products"].columns}
    asset_columns = {column.name for column in Base.metadata.tables["assets"].columns}
    version_columns = {column.name for column in Base.metadata.tables["asset_versions"].columns}
    review_columns = {column.name for column in Base.metadata.tables["reviews"].columns}
    assert {"is_archived", "archived_at"} <= product_columns
    assert {"is_archived", "archived_at"} <= asset_columns
    assert {"status", "is_deleted", "deleted_at"} <= set(version_columns)
    assert {"is_deleted", "deleted_at"} <= review_columns


def test_required_foreign_keys_are_not_nullable():
    required_columns = {
        "skus": ["product_id"],
        "assets": ["product_id"],
        "asset_versions": ["asset_id"],
        "generation_jobs": ["source_version_id"],
        "reviews": ["asset_version_id", "generation_job_id"],
        "export_bundles": ["product_id"],
    }

    for table_name, column_names in required_columns.items():
        table = Base.metadata.tables[table_name]
        assert all(not table.c[column_name].nullable for column_name in column_names)


def test_processing_tasks_allow_no_platform_rule_but_pin_workflows():
    table = Base.metadata.tables["generation_jobs"]
    assert table.c.resolved_rule_id.nullable is True
    assert table.c.workflow_definition_id.nullable is True
    targets = {foreign_key.target_fullname for foreign_key in table.foreign_keys}
    assert "workflow_definitions.id" in targets
