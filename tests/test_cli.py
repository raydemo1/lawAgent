import pytest

from law_agent.data.cli import main


def test_cli_help_exits_successfully(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "python -m law_agent.data" in captured.out


def test_manifest_validate_example(capsys) -> None:
    exit_code = main(["manifest", "validate", "data/manifests/source_manifest.example.csv"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Validated 1 sources (1 included in MVP)" in captured.out
