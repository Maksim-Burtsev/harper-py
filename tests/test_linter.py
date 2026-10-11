"""harper.js's packages/harper.js/src/Linter.test.ts (v2.11.0), ported 1:1 where it applies.

Not ported: `setup()`, `dispose()` and the Blob variants (no such API here, DEVIATIONS.md 2),
and the two WorkerLinter-vs-LocalLinter config comparisons (there is one Linter). The
"multiple synchronous requests" and "concurrent requests" tests run their calls in sequence.
"""

import base64
import io
import json
import random
import string
import zipfile

import pytest

from harper import Language, Linter


def random_string(length: int) -> str:
    return "".join(random.choice(string.ascii_letters) for _ in range(length))


def create_test_weirpack() -> dict[str, str]:
    manifest = """{
    "name": "Test Weirpack",
    "author": "Anonymous",
    "version": "0.1.0",
    "description": "",
    "license": "MIT"
  }"""
    annotations = """
    {
    	"affixes": {
    	},
    	"properties": {
    	}
    }
  """
    return {"annotations.json": annotations, "manifest.json": manifest, "dictionary.dict": "1000\n\n"}


def pack_weirpack_files(files: dict[str, str]) -> bytes:
    """harper.js's packWeirpackFiles: a deflate zip of the files."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return out.getvalue()


WEIRPACK_PASS_BASE64 = "UEsDBBQAAAAIAFR7LFx+V+AhbQAAAIgAAAANAAAAbWFuaWZlc3QuanNvbi2MMQuDMBBG9/yKI3MJdnXrWNBNcE7iaQ9DLlxil+J/l5iO33u876cAtD3Kh0X3oCfMBV5tPqr6omTiWF1nOvNsdMHshVL5m7uakSRZv8PKAjPLjjJQLCjgAjsIbBeKm2kHgTzGjDUe35NW5wVQSwMEFAAAAAgAVHssXLV8hxV2AAAAoQAAABUAAABXZWlycGFja1Rlc3RSdWxlLndlaXJNzrENwzAMBMBeUxDskx0yQMoMQEtvh7BECaKMePwYdorgyz/gH3vrVESNJrEjIWQMKnCXBcQvB4036APtTeJKHS1LRIGNO582wWPXNrQa8eNPbhk0104DPtSWH1/VEvFTPSJnMdTNr2JCrMcu8XXkNuuOxOELUEsBAhQDFAAAAAgAVHssXH5X4CFtAAAAiAAAAA0AAAAAAAAAAAAAAIABAAAAAG1hbmlmZXN0Lmpzb25QSwECFAMUAAAACABUeyxctXyHFXYAAAChAAAAFQAAAAAAAAAAAAAAgAGYAAAAV2VpcnBhY2tUZXN0UnVsZS53ZWlyUEsFBgAAAAACAAIAfgAAAEEBAAAAAA=="
WEIRPACK_FAIL_BASE64 = "UEsDBBQAAAAIABtOLVw9tWbJYgAAAH0AAAANAAAAbWFuaWZlc3QuanNvbi3LMQ9AMBCG4d2vuHSWhtVmNNgk5qYOF01J7zCI/07V+H1P3isDUGaXeQ2qAtUhC9Rp5pEODEyrj1boQpfpHZBtoE1++aoeKWzGLnCSzDAacuQnkJdYp8qRRc8Yi7bpVHY/UEsDBBQAAAAIABtOLVylaCfNfgAAALkAAAAVAAAAV2VpcnBhY2tUZXN0UnVsZS53ZWlyTY5RDsIwDEP/e4oo/3AHDsAnB+g6b0Rr06rJxI7PYICQf6z4WTG21qlEURqi7gohw6nALM4gvhnI76AHpLeYFupoOSYUqJ/5zY6w1KW5VCW+/JFrBk21k8NcdP7gi+hIfBVLyDkq6mpHMCDV/S/xMeQ0yYaRQ3jVv0f+mfAEUEsBAhQDFAAAAAgAG04tXD21ZsliAAAAfQAAAA0AAAAAAAAAAAAAAIABAAAAAG1hbmlmZXN0Lmpzb25QSwECFAMUAAAACAAbTi1cpWgnzX4AAAC5AAAAFQAAAAAAAAAAAAAAgAGNAAAAV2VpcnBhY2tUZXN0UnVsZS53ZWlyUEsFBgAAAAACAAIAfgAAAD4BAAAAAA=="


@pytest.fixture
def linter() -> Linter:
    return Linter()


def flat(organized):
    return [lint for lints in organized.values() for lint in lints]


def test_detects_repeated_words(linter):
    assert len(linter.lint("The the problem is")) == 1


def test_emits_organized_lints_the_same_as_it_emits_normal_lints(linter):
    source = "The the problem is..."

    assert len(linter.lint(source)) > 0

    flattened = flat(linter.organized_lints(source))
    normal = linter.lint(source)

    assert len(flattened) == 2
    assert len(flattened) == len(normal)
    assert len(flattened[0].message) != 0


def test_deduplicates_no_more_lints_than_raw_lint_output(linter):
    source = "outstandin g"
    default_lints = linter.lint(source)
    explicit_lints = linter.lint(source, dedup=True)
    raw_lints = linter.lint(source, dedup=False)

    assert len(explicit_lints) == len(default_lints)
    assert len(default_lints) <= len(raw_lints)


def test_deduplicates_no_more_lints_than_raw_organized_output(linter):
    source = "outstandin g"
    default_lints = flat(linter.organized_lints(source))
    explicit_lints = flat(linter.organized_lints(source, dedup=True))
    raw_lints = flat(linter.organized_lints(source, dedup=False))

    assert len(explicit_lints) == len(default_lints)
    assert len(default_lints) <= len(raw_lints)


def test_detects_repeated_words_with_multiple_requests(linter):
    results = [
        linter.lint("The problem is that that"),
        linter.lint("The problem is"),
        linter.lint("The the problem is"),
    ]

    assert len(results[0]) == 1
    assert len(results[0][0].suggestions) == 1
    assert len(results[1]) == 0
    assert len(results[2]) == 1


def test_detects_lorem_ipsum_paragraph_as_not_english(linter):
    result = linter.is_likely_english(
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
    )

    assert result is False


def test_can_ignore_non_english_text_in_lint_outputs(linter):
    source = "En la mañana, como a dish de los huevos, un poquito of tocino, y a lot of leche."

    default_lints = linter.lint(source, language=Language.PLAINTEXT)
    english_only_lints = linter.lint(source, language=Language.PLAINTEXT, isolate_english=True)
    default_organized = flat(linter.organized_lints(source, language=Language.PLAINTEXT))
    english_only_organized = flat(
        linter.organized_lints(source, language=Language.PLAINTEXT, isolate_english=True)
    )

    assert len(default_lints) > 0
    assert len(default_organized) > 0
    assert english_only_lints == []
    assert english_only_organized == []


def test_contains_configuration_option_for_repetition(linter):
    assert "RepeatedWords" in linter.get_lint_config()


def test_can_set_its_configuration_away_and_to_default(linter):
    lint_config = linter.get_lint_config()
    for key in lint_config:
        lint_config[key] = True

    linter.set_lint_config(lint_config)
    lint_config = linter.get_lint_config()
    for key in lint_config:
        lint_config[key] = None

    linter.set_lint_config(lint_config)
    lint_config = linter.get_lint_config()
    for value in lint_config.values():
        assert value is None


def test_can_both_get_and_set_its_configuration(linter):
    lint_config = linter.get_lint_config()
    for key in lint_config:
        lint_config[key] = True

    linter.set_lint_config(lint_config)
    lint_config = linter.get_lint_config()
    for value in lint_config.values():
        assert value is True


def test_can_make_things_title_case(linter):
    assert linter.to_title_case("this is a test for making titles") == "This Is a Test for Making Titles"


def test_can_get_rule_descriptions(linter):
    assert isinstance(linter.get_lint_descriptions(), dict)


def test_can_get_rule_descriptions_in_html(linter):
    assert isinstance(linter.get_lint_descriptions_html(), dict)


def test_rule_descriptions_are_not_empty(linter):
    for value in linter.get_lint_descriptions().values():
        assert isinstance(value, str)
        assert len(value) != 0


def test_default_lint_config_has_no_null_values(linter):
    for value in linter.get_default_lint_config().values():
        assert value is not None


def test_can_get_structured_lint_config(linter):
    structured_config = linter.get_structured_lint_config()
    first_group = next((s for s in structured_config["settings"] if "Group" in s), None)

    assert isinstance(structured_config, dict)
    assert isinstance(structured_config["settings"], list)
    assert len(structured_config["settings"]) > 0
    assert first_group is not None
    assert isinstance(first_group["Group"]["description"], str)
    assert len(first_group["Group"]["description"]) > 0


def test_structured_lint_config_json_round_trips(linter):
    # "structured lint config JSON parses" / "JSON and object agree": the JSON twin is json.dumps.
    structured_config = linter.get_structured_lint_config()
    assert json.loads(json.dumps(structured_config)) == structured_config


def test_can_generate_lint_context_hashes(linter):
    source = "This is an test."
    lints = linter.lint(source)

    assert len(lints) >= 1
    assert isinstance(linter.context_hash(source, lints[0]), int)


def test_can_ignore_lints(linter):
    source = "This is an test."
    first_round = linter.lint(source)

    assert len(first_round) >= 1

    linter.ignore_lint(source, first_round[0])
    second_round = linter.lint(source)

    assert len(second_round) < len(first_round)


def test_can_ignore_multiple_lints(linter):
    source = "This is an test of exprting lints."
    first_round = linter.lint(source)

    assert len(first_round) >= 2

    linter.ignore_lints(source, first_round)

    assert len(linter.lint(source)) == 0


def test_can_ignore_lints_with_hashes(linter):
    source = "This is an test."
    first_round = linter.lint(source)

    assert len(first_round) >= 1

    linter.ignore_lint_hash(linter.context_hash(source, first_round[0]))
    second_round = linter.lint(source)

    assert len(second_round) < len(first_round)


def test_can_ignore_larger_lints_to_reveal_smaller_ones(linter):
    source = 'This is a really long sentensd with some errorz in it, which in an old version of Harper, would get removedd when the bigger "Long Sentences" lint was ignored, that isn\'t what we woant, so we are writing a test for that exact problem.'

    first_round = linter.lint(source)
    assert len(first_round) >= 1

    linter.ignore_lint(source, first_round[0])

    assert len(linter.lint(source)) == 4


def test_can_reimport_ignored_lints():
    source = "This is an test of exprting lints."

    first_linter = Linter()
    first_lints = first_linter.lint(source)
    for lint in first_lints:
        first_linter.ignore_lint(source, lint)

    exported = first_linter.export_ignored_lints()

    second_linter = Linter()
    second_linter.import_ignored_lints(exported)
    second_lints = second_linter.lint(source)

    assert len(first_lints) > len(second_lints)
    assert len(second_lints) == 0


def test_can_add_words_to_the_dictionary(linter):
    source = "asdf is not a word"

    assert len(linter.lint(source)) == 1

    linter.import_words(["asdf"])

    assert len(linter.lint(source)) == 0


def test_allows_correct_capitalization_of_united_states(linter):
    assert len(linter.lint("The United States is a big country.")) == 0


def test_can_summarize_simple_stat_records(linter):
    source = "This is an test."
    lint = linter.lint(source)[0]
    sug = lint.suggestions[0]

    assert linter.apply_suggestion(source, lint, sug) == "This is a test."
    assert isinstance(linter.summarize_stats(), dict)


def test_can_save_and_restore_stat_records(linter):
    source = "This is an test."
    lint = linter.lint(source)[0]
    sug = lint.suggestions[0]

    assert linter.apply_suggestion(source, lint, sug) == "This is a test."

    stats = linter.generate_stats_file()
    new_linter = Linter()
    new_linter.import_stats_file(stats)


def test_emits_the_correct_span_indices(linter):
    text = "✉️👋👍✉️🚀✉️🌴 This is to show the offset issue sdssda is it there?"

    span = linter.lint(text)[0].span

    # harper.js: 48..54 in UTF-16 code units. Here: code points (DEVIATIONS.md 1).
    assert (span.start, span.end) == (44, 50)
    assert text[span.start : span.end] == "sdssda"


def test_lints_headings_when_forced_to_mark_them_as_such(linter):
    text = "This sentences should be forced to title case."

    lints = linter.lint(text, force_all_headings=True)

    assert len(lints) == 1
    assert lints[0].lint_kind == "Capitalization"
    assert lints[0].problem_text == text


def test_lints_headings_when_forced_to_mark_them_as_such_with_organized_mode(linter):
    text = "This sentences should be forced to title case."

    title_case_lints = linter.organized_lints(text, force_all_headings=True)["UseTitleCase"]

    assert len(title_case_lints) == 1
    assert title_case_lints[0].lint_kind == "Capitalization"
    assert title_case_lints[0].problem_text == text


def test_will_lint_many_random_strings_with_a_single_instance(linter):
    for _ in range(250):
        assert linter.organized_lints(random_string(10)) is not None


def test_can_load_weirpacks_from_bytes(linter):
    failures = linter.load_weirpack(base64.b64decode(WEIRPACK_PASS_BASE64))

    assert failures is None
    assert len(linter.organized_lints("banana")["WeirpackTestRule"]) == 1


def test_rejects_weirpacks_with_failing_tests(linter):
    failures = linter.load_weirpack(base64.b64decode(WEIRPACK_FAIL_BASE64))

    assert isinstance(failures, dict)
    assert failures["WeirpackTestRule"][0]["expected"] == "banana"
    assert "WeirpackTestRule" not in linter.organized_lints("banana")


def test_can_exclude_things_with_regex_in_organized_lint_function(linter):
    source = "This text contains errorz."

    assert len(flat(linter.organized_lints(source))) == 1
    assert len(flat(linter.organized_lints(source, regex_mask="errorz"))) == 0


def test_returns_correct_suggestion_for_ned_with_organized_lints(linter):
    flattened = flat(linter.organized_lints("I don't ned it."))

    assert len(flattened) == 1
    assert "need" in [s.replacement_text for s in flattened[0].suggestions]


def test_can_exclude_things_with_regex_in_normal_lint_function(linter):
    source = "This text contains errorz."

    assert len(linter.lint(source)) == 1
    assert len(linter.lint(source, regex_mask="errorz")) == 0


def test_returns_correct_suggestion_for_ned(linter):
    lints = linter.lint("I don't ned it.")

    assert len(lints) == 1
    assert "need" in [s.replacement_text for s in lints[0].suggestions]


def test_can_load_dictionaries_from_weirpacks(linter):
    source = "I adore this akljsfhl group!"

    assert len(linter.lint(source)) == 1

    weirpack = create_test_weirpack()
    weirpack["dictionary.dict"] = "1000\n\nakljsfhl"
    linter.load_weirpack(pack_weirpack_files(weirpack))

    assert len(linter.lint(source)) == 0


def test_can_request_a_typst_parser(linter):
    lints = linter.lint(
        """
= Hello, world!

This is a simple Typst document.

- Item one
- Item two
- Item three
      """,
        language=Language.TYPST,
    )

    assert lints == []
