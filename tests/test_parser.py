import json
from datetime import timezone
from pathlib import Path

from tokenscope.parser import ParseResult, find_transcripts, iter_lines, parse_path, parse_timestamp

SAMPLES = Path(__file__).resolve().parents[1] / "examples" / "sample-transcripts"


def _assistant(msg_id="msg_1", tools=(), **usage):
    return json.dumps({
        "type": "assistant",
        "sessionId": "s1",
        "timestamp": "2026-11-03T10:00:00Z",
        "message": {
            "id": msg_id,
            "model": "claude-sonnet-5-5",
            "usage": usage,
            "content": [{"type": "tool_use", "name": t, "input": {}} for t in tools],
        },
    })


def test_finds_every_sample_transcript():
    files = find_transcripts(SAMPLES)
    assert len(files) == 7
    assert {f.parent.name for f in files} == {"demo-webapp", "data-pipeline", "cli-toolkit"}


def test_single_file_path_is_accepted():
    one = find_transcripts(SAMPLES)[0]
    assert find_transcripts(one) == [one]
    assert find_transcripts(SAMPLES / "does-not-exist") == []


def test_sample_parse_skips_the_malformed_line_and_keeps_going():
    result = parse_path(SAMPLES)
    assert result.files == 7
    assert result.skipped == 1
    assert {t.project for t in result.turns} == {"demo-webapp", "data-pipeline", "cli-toolkit"}
    assert all(t.timestamp is not None and t.model for t in result.turns)


def test_garbage_lines_are_counted_not_fatal():
    result = ParseResult()
    lines = ["", "not json", "[1, 2, 3]", '"a string"', _assistant(output_tokens=5)]
    turns = list(iter_lines(lines, "p", "fallback", result))
    assert len(turns) == 1
    assert result.lines == 4
    assert result.skipped == 3


def test_repeated_message_id_counts_usage_once_but_keeps_tools():
    result = ParseResult()
    lines = [
        _assistant("msg_a", tools=["Read"], input_tokens=10, output_tokens=100),
        _assistant("msg_a", tools=["Edit"], input_tokens=10, output_tokens=100),
    ]
    turns = list(iter_lines(lines, "p", "fallback", result))
    assert sum(t.output_tokens for t in turns) == 100
    assert [name for t in turns for name in t.tools] == ["Read", "Edit"]


def test_user_lines_and_bad_numbers_are_ignored():
    result = ParseResult()
    user = json.dumps({"type": "user", "message": {"role": "user", "content": "hi", "usage": {"input_tokens": 99}}})
    weird = _assistant("msg_w", input_tokens=-5, output_tokens="12", cache_read_input_tokens=True)
    turns = list(iter_lines([user, weird], "p", "fallback", result))
    assert len(turns) == 1
    t = turns[0]
    assert (t.input_tokens, t.output_tokens, t.cache_read_tokens) == (0, 0, 0)


def test_missing_session_id_falls_back_to_file_stem():
    result = ParseResult()
    line = json.dumps({"message": {"model": "m", "usage": {"output_tokens": 1}}})
    (turn,) = iter_lines([line], "proj", "file-stem", result)
    assert turn.session_id == "file-stem"
    assert turn.timestamp is None


def test_parse_timestamp_variants():
    ts = parse_timestamp("2026-11-03T10:00:00.250Z")
    assert ts is not None and ts.tzinfo == timezone.utc and ts.hour == 10
    assert parse_timestamp("2026-11-03T10:00:00+02:00").hour == 8
    assert parse_timestamp("2026-11-03T10:00:00").tzinfo == timezone.utc
    assert parse_timestamp("yesterday-ish") is None
    assert parse_timestamp(12345) is None
