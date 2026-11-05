AUDIT_EVENTS = frozenset(
    "reports.report." + action
    for action in (
        "requested",
        "defined",
        "ingested",
        "verified",
        "activated",
        "completed",
        "quarantined",
        "blocked",
        "exported",
        "started",
        "failed",
        "cancelled",
        "retried",
        "artifact_staged",
        "artifact_published",
        "temporary_cleaned",
        "gst.reviewed",
        "gst.externally_filed",
    )
)
