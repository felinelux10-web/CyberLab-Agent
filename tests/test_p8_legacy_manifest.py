def test_legacy_manifest_keeps_compatibility_paths_classified():
    from lab_v4_dev.legacy_manifest import (
        CANONICAL_ENTRYPOINT,
        active_runtime_entrypoint,
        classify,
    )

    assert active_runtime_entrypoint() == CANONICAL_ENTRYPOINT
    root = classify("lab_v4/")
    assert root is not None
    assert root.status == "legacy_compatibility"
    assert root.callers == ()
    assert root.replacement == "lab_v4_dev/"
    assert "do not add new imports" in root.notes
    assert "candidate for archival" in root.notes

    item = classify("lab_v4/llm/groq_client.py")
    assert item is not None
    assert item.status == "legacy_direct_provider"
    assert item.callers == ()
    assert item.replacement == "lab_v4_dev/llm/gateway.py"
    assert classify("lab_v4_dev/llm/gateway.py") is None
