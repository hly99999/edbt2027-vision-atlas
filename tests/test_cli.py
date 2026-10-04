import json
import io
import sys

import pytest

from db_theory_atlas.cli import main
from db_theory_atlas.sources import canonical_paper_id
from test_collision import SOURCE_METADATA
from test_index import atlas_index, committed_index_repo
from test_problems import original_problem


@pytest.fixture()
def index_selector(tmp_path, monkeypatch):
    _, selector = committed_index_repo(tmp_path, monkeypatch)
    return selector


@pytest.mark.parametrize("command", [
    "search", "paper", "theorem", "open", "topic", "collision", "descendants", "unresolved",
])
def test_all_commands_have_useful_help(command, capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main([command, "--help"])
    assert caught.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()


def test_search_and_exact_open_output_are_stable_json(index_selector, capsys) -> None:
    assert main(["--index", index_selector, "search", "minimal distinguishing database"]) == 0
    first = capsys.readouterr().out
    assert main(["--index", index_selector, "search", "minimal distinguishing database"]) == 0
    assert capsys.readouterr().out == first

    assert main(["--index", index_selector, "open", original_problem().problem_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["problem_id"] == original_problem().problem_id


def test_expected_errors_use_explicit_exit_codes_without_tracebacks(index_selector, capsys) -> None:
    assert main(["--index", index_selector, "paper", "paper:missing"]) == 3
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()
    assert "traceback" not in captured.err.lower()

    assert main(["--index", index_selector, "search", "unknown-never-indexed"]) == 4
    assert "no indexed record" in capsys.readouterr().err.lower()


def test_unresolved_and_descendants_commands(index_selector, capsys) -> None:
    assert main(["--index", index_selector, "unresolved"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] != "RESOLVED"

    assert main(["--index", index_selector, "descendants", original_problem().problem_id]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_invalid_index_is_reported_without_traceback(index_selector, tmp_path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version":1}', encoding="utf-8")
    assert main(["--index", str(path), "unresolved"]) == 2
    captured = capsys.readouterr()
    assert "invalid index" in captured.err.lower()
    assert "traceback" not in captured.err.lower()


def test_all_eight_commands_have_success_paths(index_selector, capsys) -> None:
    index = atlas_index()
    identifiers = {
        "paper": canonical_paper_id(SOURCE_METADATA),
        "theorem": "theorem:resolution-2",
        "open": original_problem().problem_id,
        "topic": "topic:arity-frontier",
        "collision": next(item.record_id for item in index.records if item.record_type == "COLLISION"),
    }
    commands = (
        ["search", "minimal distinguishing database"],
        ["paper", identifiers["paper"]],
        ["theorem", identifiers["theorem"]],
        ["open", identifiers["open"]],
        ["topic", identifiers["topic"]],
        ["collision", identifiers["collision"]],
        ["descendants", identifiers["paper"], "--relation", "CITES", "--type", "PAPER"],
        ["unresolved", "--category", "HIGH_VALUE_FEASIBLE"],
    )
    for command in commands:
        assert main(["--index", index_selector, *command]) == 0
        json.loads(capsys.readouterr().out)


def test_cli_ignores_environment_index_override_and_rejects_unlisted_selector(
    index_selector, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("DBTA_INDEX", "../attacker.json")
    assert main(["unresolved"]) == 0
    assert json.loads(capsys.readouterr().out)
    assert main(["--index", "../attacker.json", "unresolved"]) == 2
    assert "manifest" in capsys.readouterr().err.lower() or "selector" in capsys.readouterr().err.lower()


def test_cli_reconfigures_stdout_utf8_and_captures_encoding_errors(index_selector, monkeypatch) -> None:
    class Reconfigurable(io.StringIO):
        configured = None

        def reconfigure(self, **kwargs):
            self.configured = kwargs

    output = Reconfigurable()
    error = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "stderr", error)
    assert main(["--index", index_selector, "unresolved"]) == 0
    assert output.configured["encoding"].lower() == "utf-8"

    class BrokenOutput(Reconfigurable):
        def write(self, value):
            raise UnicodeEncodeError("ascii", value, 0, 1, "cannot encode")

    monkeypatch.setattr(sys, "stdout", BrokenOutput())
    assert main(["--index", index_selector, "unresolved"]) == 2
    assert "encoding" in error.getvalue().lower() or "output" in error.getvalue().lower()
