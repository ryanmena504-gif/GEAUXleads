"""The re-evaluation script does not touch Airtable unless asked."""
from scripts.reevaluate_no_contact_passes import main


def test_default_invocation_does_not_connect(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Not connected" in out
    assert "--apply" in out
