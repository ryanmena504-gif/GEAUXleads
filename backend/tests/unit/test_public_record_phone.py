"""The public-record phone hook stays free and does nothing until a source exists."""
from services.public_record_phone import lookup_public_record_phone


def test_lookup_returns_none_and_does_not_invent_a_number():
    assert lookup_public_record_phone({
        "owner": "Ada Lovelace",
        "project_address": "2100 Saint Charles Ave",
        "source": "Permit",
    }) is None
