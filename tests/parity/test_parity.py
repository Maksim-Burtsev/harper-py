"""Golden parity with harper-cli 2.11.0: same rules, spans, messages and suggestions.

harper-cli reports character (code point) offsets, which are this package's span units.
`regen.py` rebuilds expected.json from the CLI.
"""

import json
import pathlib

import pytest

from harper import Language, Linter, SuggestionKind

HERE = pathlib.Path(__file__).parent
CORPUS = json.loads((HERE / "corpus.json").read_text("utf-8"))
EXPECTED = json.loads((HERE / "expected.json").read_text("utf-8"))
LINTER = Linter()


def cli_suggestion(s) -> str:
    """harper-core's `Display for Suggestion`, which harper-cli prints."""
    if s.kind is SuggestionKind.REPLACE:
        return f"Replace with: “{s.replacement_text}”"
    if s.kind is SuggestionKind.INSERT_AFTER:
        return f"Insert “{s.replacement_text}”"
    return "Remove error"


def test_corpus_matches_expected():
    assert len(EXPECTED) == len(CORPUS) >= 50


@pytest.mark.parametrize("case,expected", list(zip(CORPUS, EXPECTED)), ids=[e["file"] for e in EXPECTED])
def test_same_lints_as_harper_cli(case, expected):
    got = [
        {
            "rule": rule,
            "kind": lint.lint_kind_pretty,
            "span": {"char_start": lint.span.start, "char_end": lint.span.end},
            "message": lint.message,
            "suggestions": [cli_suggestion(s) for s in lint.suggestions],
            "matched_text": lint.problem_text,
        }
        for rule, lints in LINTER.organized_lints(case["text"], language=Language(case["language"])).items()
        for lint in lints
    ]
    assert got == expected["lints"]
