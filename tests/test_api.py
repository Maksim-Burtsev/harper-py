"""What this binding adds on top of harper.js: Python types, errors, code point spans."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import harper
from harper import Dialect, Language, Linter, Span, SuggestionKind

LINTER = Linter()


def test_issue_2216_word_from_another_dialect_is_accepted():
    # harper-wasm's own Rust test.
    linter = Linter()
    linter.import_words(["Aeon"])
    assert linter.lint("Aeon", language=Language.PLAINTEXT) == []


def test_module_functions_match_methods():
    assert harper.to_title_case("the old man and the sea") == LINTER.to_title_case("the old man and the sea")
    assert harper.get_default_lint_config() == LINTER.get_default_lint_config()


def test_lint_attributes_and_repr():
    text = "This is an test."
    (lint,) = LINTER.lint(text)
    assert lint.span == Span(8, 10)
    assert lint.span.len() == 2 and not lint.span.is_empty()
    assert lint.problem_text == "an"
    assert lint.lint_kind == "Miscellaneous"
    assert isinstance(lint.lint_kind_pretty, str)
    assert lint.message and lint.message_html
    assert lint.suggestion_count == len(lint.suggestions) == 1
    (sug,) = lint.suggestions
    assert sug.kind is SuggestionKind.REPLACE
    assert sug.replacement_text == "a"
    assert sug == lint.suggestions[0] and hash(sug) == hash(lint.suggestions[0])
    assert repr(lint.span) == "Span(start=8, end=10)"
    assert repr(sug) == "Suggestion(kind=SuggestionKind.REPLACE, replacement_text='a')"
    assert repr(lint).startswith("Lint(lint_kind='Miscellaneous', span=Span(start=8, end=10), problem_text='an'")


def test_span_is_frozen():
    with pytest.raises(AttributeError):
        Span(1, 2).start = 0


def test_language_accepts_harper_js_strings():
    text = "# a heading\n\nThis is an test."
    assert len(LINTER.lint(text, language="markdown")) == len(LINTER.lint(text))
    assert LINTER.lint("This is an test.", language="plaintext")[0].problem_text == "an"


def test_unknown_language_warns_and_uses_markdown():
    with pytest.warns(UserWarning, match="Unknown Harper language 'latex'; using markdown."):
        lints = LINTER.lint("This is an test.", language="latex")
    assert len(lints) == 1


def test_invalid_regex_mask_warns_and_returns_nothing():
    with pytest.warns(UserWarning, match="regex mask is invalid"):
        assert LINTER.lint("This is an test.", regex_mask="(") == []
    with pytest.warns(UserWarning, match="regex mask is invalid"):
        assert LINTER.organized_lints("This is an test.", regex_mask="(") == {}


def test_upstream_errors_are_value_errors():
    linter = Linter()
    with pytest.raises(ValueError):
        linter.set_lint_config({"RepeatedWords": "yes"})
    with pytest.raises(ValueError):
        linter.import_ignored_lints("not json")
    with pytest.raises(ValueError):
        linter.import_stats_file("not a stats file\n")
    with pytest.raises(ValueError):
        linter.load_weirpack(b"not a zip")


def test_dialect_property_rebuilds_like_set_dialect():
    linter = Linter(dialect=Dialect.BRITISH)
    assert linter.dialect is Dialect.BRITISH
    assert len(linter.lint("I like the color red.")) == 1

    linter.import_words(["asdf"])
    linter.dialect = Dialect.BRITISH  # same dialect: nothing happens
    assert linter.export_words() == ["asdf"]

    linter.dialect = Dialect.AMERICAN  # different dialect: a fresh linter, as in harper.js
    assert linter.dialect is Dialect.AMERICAN
    assert linter.export_words() == []
    assert linter.lint("I like the color red.") == []


def test_words_round_trip():
    linter = Linter()
    linter.import_words(["asdf", "qwer"])
    assert sorted(linter.export_words()) == ["asdf", "qwer"]
    linter.clear_words()
    assert linter.export_words() == []


def test_clear_ignored_lints():
    linter = Linter()
    source = "This is an test."
    linter.ignore_lint(source, linter.lint(source)[0])
    assert linter.lint(source) == []
    linter.clear_ignored_lints()
    assert len(linter.lint(source)) == 1


def test_summarize_stats_time_window():
    linter = Linter()
    source = "This is an test of exprting lints."
    lint = next(l for l in linter.lint(source) if l.lint_kind == "Spelling")
    linter.apply_suggestion(source, lint, lint.suggestions[0])
    summary = linter.summarize_stats()
    assert summary["total_applied"] == 1
    assert summary["lint_counts"] == {"Spelling": 1}
    assert summary["misspelled"] == {"exprting": 1}
    assert linter.summarize_stats(start=2**40)["total_applied"] == 0
    assert linter.summarize_stats(end=0)["total_applied"] == 0


def test_isolate_english():
    assert isinstance(LINTER.isolate_english("En la mañana, I ate a dish."), str)


def test_lone_surrogates_become_replacement_characters():
    # wasm-bindgen does the same to a JS string; indices still count one per code point.
    text = "\ud800 This is an test."
    (lint,) = LINTER.lint(text)
    assert text[lint.span.start : lint.span.end] == "an"
    assert LINTER.apply_suggestion(text, lint, lint.suggestions[0]) == "� This is a test."


@settings(max_examples=300, deadline=None)
@given(
    st.text(st.characters(exclude_categories=["Cs"]), max_size=80)
    | st.lists(st.sampled_from(["the", "The", "an", "teh", "👋", "✉️", "日本語", " ", "\n", ".", "#", "*", "é"]), max_size=40).map("".join)
)
def test_span_invariant_on_random_unicode(text):
    for language in Language:
        for lint in LINTER.lint(text, language=language, dedup=False):
            assert text[lint.span.start : lint.span.end] == lint.problem_text
        for lints in LINTER.organized_lints(text, language=language).values():
            for lint in lints:
                assert text[lint.span.start : lint.span.end] == lint.problem_text
