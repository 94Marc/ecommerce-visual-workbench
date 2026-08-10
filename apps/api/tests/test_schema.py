from app.core.database import Base


def test_phase_one_schema_contains_all_domain_tables():
    expected = {
        "products",
        "skus",
        "assets",
        "asset_versions",
        "platform_rules",
        "generation_jobs",
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
    assert "platform_rules.id" in targets


def test_required_foreign_keys_are_not_nullable():
    required_columns = {
        "skus": ["product_id"],
        "assets": ["product_id"],
        "asset_versions": ["asset_id"],
        "generation_jobs": ["source_version_id", "resolved_rule_id"],
        "reviews": ["asset_version_id", "generation_job_id"],
        "export_bundles": ["product_id"],
    }

    for table_name, column_names in required_columns.items():
        table = Base.metadata.tables[table_name]
        assert all(not table.c[column_name].nullable for column_name in column_names)
