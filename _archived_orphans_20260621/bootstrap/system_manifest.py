SYSTEM_VERSION = "v5.2.2"

CONTEXT_POLICY = {
    "single_source_of_truth": True,
    "allowed_versions": ["v5.0", "v5.1", "v5.2.0", "v5.2.1", "v5.2.2"],
    "default_version": SYSTEM_VERSION,
}

SESSION_POLICY = {
    "allow_legacy_sessions": False,
    "invalidate_on_boot": True,
}

CRITICALITY_SCHEMA = {
    "status": "success",
    "schema": ["text"],
    "strict": True,
}
