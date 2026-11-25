import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from rich.console import Console

from tokenscope.cli import main
from tokenscope.parser import Turn, parse_path
from tokenscope.render import human, sparkline
from tokenscope.stats import summarize

SAMPLES = Path(__file__).resolve().parents[1] / "examples" / "sample-transcripts"


@pytest.fixture(scope="module")
def turns():
    return parse_path(SAMPLES).turns


def test_groupings_add_up_to_the_total(turns):
    s = summarize(turns)
    assert s.total.turns > 0
    for groups in (s.by_model, s.by_project, s.by_day):
        assert sum(b.total_tokens for b in groups.values()) == s.total.total_tokens
        assert sum(b.cost for b in groups.values()) == pytest.approx(s.total.cost)
    assert sum(sess.cost for sess in s.sessions.values()) == pytest.approx(s.total.cost)
    assert len(s.sessions) == 7


def test_since_drops_earlier_days(turns):
    full = summarize(turns)
    later = summarize(turns, since=date(2026, 11, 6))
    assert min(later.by_day) >= date(2026, 11, 6)
    assert later.total.total_tokens < full.total.total_tokens
    assert summarize(turns, since=date(2030, 1, 1)).total.turns == 0


def test_top_sessions_are_sorted_by_cost(turns):
    top = summarize(turns).top_sessions(3)
    assert len(top) == 3
    assert [s.cost for s in top] == sorted((s.cost for s in top), reverse=True)


def test_tool_counts_include_lines_without_usage():
    t = Turn(project="p", session_id="s", timestamp=datetime(2026, 11, 1, tzinfo=timezone.utc), model="m", tools=["Bash", "Bash"])
    s = summarize([t])
    assert s.tools["Bash"] == 2
    assert s.total.turns == 0


def test_json_output_is_valid_and_honours_top(capsys):
    assert main(["--path", str(SAMPLES), "--json", "--top", "2"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) >= {"total", "by_model", "by_project", "by_day", "top_tools", "top_sessions", "meta"}
    assert len(data["top_tools"]) == 2
    assert len(data["top_sessions"]) == 2
    assert data["meta"]["skipped_lines"] == 1
    assert set(data["by_project"]) == {"demo-webapp", "data-pipeline", "cli-toolkit"}


def test_dashboard_renders_every_section():
    console = Console(record=True, width=100, force_terminal=False)
    assert main(["--path", str(SAMPLES), "--top", "3"], console=console) == 0
    text = console.export_text()
    for heading in ("By model", "By project", "By day (UTC)", "Top 3 tools", "most expensive sessions", "est cost"):
        assert heading in text
    assert "data-pipeline" in text


def test_empty_folder_says_so(tmp_path):
    console = Console(record=True, width=80)
    assert main(["--path", str(tmp_path)], console=console) == 0
    assert "No usage found" in console.export_text()


def test_bad_inputs(tmp_path):
    assert main(["--path", str(tmp_path / "nope")]) == 2
    with pytest.raises(SystemExit):
        main(["--path", str(SAMPLES), "--since", "11/05/2026"])
    with pytest.raises(SystemExit):
        main(["--path", str(SAMPLES), "--top", "0"])


def test_helpers():
    assert human(999) == "999"
    assert human(1_500) == "1.50k"
    assert human(2_340_000) == "2.34M"
    assert sparkline([0, 5, 10]) == " ▄█"
    assert sparkline([]) == ""
