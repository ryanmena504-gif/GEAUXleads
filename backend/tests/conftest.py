import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# These suites assert against the bundled sample fixture (opp_001-style IDs,
# fixed record counts). They are meaningless against the live Airtable base.
SAMPLE_FIXTURE_ONLY = {
    "test_governed_buckets.py",
    "test_iteration_9_governed_leaks.py",
    "test_iteration_10_no_write_on_draft.py",
}


def pytest_collection_modifyitems(config, items):
    if os.environ.get("AIRTABLE_ENABLED", "").lower() != "true":
        return
    skip = pytest.mark.skip(reason="sample-fixture-only suite; backend is wired to live Airtable")
    for item in items:
        if Path(str(item.fspath)).name in SAMPLE_FIXTURE_ONLY:
            item.add_marker(skip)
