# harper-py guide

The tour of everything `harper.Linter` does. The API is harper.js's `Linter` interface,
synchronous and in snake_case; [DEVIATIONS.md](../DEVIATIONS.md) lists every difference.

## One linter, reused

```python
from harper import Linter, Dialect

linter = Linter()                          # American English
british = Linter(dialect=Dialect.BRITISH)
```

Construction builds Harper's curated dictionary: about 0.2 s for the first `Linter` in a
process, a few milliseconds for the next ones. Create one and keep it; linting a page of
text then takes tens of milliseconds.

## Linting

```python
lints = linter.lint("This is an test.")
lint = lints[0]
lint.span            # Span(start=8, end=10)
lint.problem_text    # 'an'
lint.lint_kind       # 'Miscellaneous' (a key; lint_kind_pretty is for display)
lint.message         # 'Incorrect indefinite article.'
lint.message_html    # the same message as HTML
lint.suggestions     # [Suggestion(kind=SuggestionKind.REPLACE, replacement_text='a')]
```

`span` counts Python `str` indices, so `text[lint.span.start:lint.span.end]` is always
`lint.problem_text`, whatever the text contains.

The keyword arguments are harper.js's `LintOptions`, with the same defaults:

| Argument | Default | What it does |
| --- | --- | --- |
| `language` | `Language.MARKDOWN` | `PLAINTEXT`, `MARKDOWN` or `TYPST`; harper.js's strings (`"plaintext"`, …) work too. Markdown code blocks, inline code and link targets are not checked. |
| `regex_mask` | `None` | Text matching this regular expression is skipped. An invalid pattern warns and returns `[]`. |
| `force_all_headings` | `False` | Treat every line as a heading, so title-case rules apply. |
| `dedup` | `True` | Remove overlapping lints. |
| `isolate_english` | `False` | Skip text that does not look like English. |

```python
text = "See JIRA-1234 now."
linter.lint(text)                              # flags 'JIRA'
linter.lint(text, regex_mask=r"[A-Z]+-\d+")    # []
```

`organized_lints` takes the same arguments and keys the lints by the rule that produced
them; every rule is present, most with an empty list:

```python
groups = linter.organized_lints("The the problem is...")
{rule: lints for rule, lints in groups.items() if lints}
# {'RepeatedWords': [Lint(...'The the'...)], 'UseEllipsisCharacter': [Lint(...'...'...)]}
```

## Applying suggestions

```python
text = "This is an test."
lint = linter.lint(text)[0]
linter.apply_suggestion(text, lint, lint.suggestions[0])    # 'This is a test.'
```

A suggestion is `REPLACE` (the span with `replacement_text`), `REMOVE` (the span), or
`INSERT_AFTER` (`replacement_text` after the span). Each applied suggestion is recorded in
the linter's statistics (below).

## Rules

```python
config = linter.get_lint_config()        # {'AnA': None, ..., 'SpellCheck': None, ...}
linter.set_lint_config({**config, "SpellCheck": False})
```

A rule is `True` (on), `False` (off) or `None` (Harper's default for it).
`get_default_lint_config()` shows those defaults, `get_lint_descriptions()` (Markdown) and
`get_lint_descriptions_html()` explain each rule, and `get_structured_lint_config()`
groups the rules with labels for a settings screen. Changes always go through
`set_lint_config`, which replaces the whole configuration: pass every rule you want to
keep.

## Dialects

```python
british.lint("I like the color of the center.")
# 'color' -> 'colour', 'center' -> 'centre'
```

`linter.dialect` reads the dialect; assigning a different one gives you a fresh linter,
exactly like harper.js's `setDialect`: words, ignored lints, configuration, Weirpacks and
statistics are reset.

## Your own words

```python
linter.import_words(["Kubernetes", "PyO3"])
linter.export_words()     # ['Kubernetes', 'PyO3'] (in no particular order)
linter.clear_words()
```

Importing rebuilds the dictionary, so add words in batches rather than one by one.

## Ignoring lints

```python
text = "This is an test."
lint = linter.lint(text)[0]
linter.ignore_lint(text, lint)       # or ignore_lints(text, lints)
linter.lint(text)                    # []

saved = linter.export_ignored_lints()     # '{"context_hashes":[...]}'
other = Linter()
other.import_ignored_lints(saved)
```

An ignored lint is identified by a hash of the lint and its surrounding words, not by its
position, so it stays ignored when text elsewhere in the document changes. `context_hash(text, lint)`
gives that hash and `ignore_lint_hash(hash)` ignores by it; `clear_ignored_lints()` forgets
all of them.

## Saving lints

```python
from harper import Lint
data = lint.to_json()              # str; Suggestion and Span have to_json too
restored = Lint.from_json(data)    # works with apply_suggestion, ignore_lint, ...
```

This is harper-wasm's JSON format, except that spans count code points, not UTF-16 units.

## Statistics

```python
linter.summarize_stats()
# {'lint_counts': {'Miscellaneous': 1}, 'total_applied': 1, 'final_config': {}, 'misspelled': {}}
log = linter.generate_stats_file()        # one JSON record per line; append-friendly
Linter().import_stats_file(log)
```

`summarize_stats(start, end)` counts only records strictly after `start` and before `end`
(Unix seconds).

## Weirpacks

A [Weirpack](https://writewithharper.com/docs/weir#Weirpacks) is a zip of extra rules
written in Harper's Weir language, with optional dictionary words and tests:

```python
failures = linter.load_weirpack(open("rules.weirpack", "rb").read())
if failures:     # {rule: [{'expected': ..., 'got': ...}]}; nothing was loaded
    ...
```

`None` means the pack's tests passed and its rules and words are now active.

## Other helpers

```python
from harper import to_title_case
to_title_case("the lord of the rings")              # 'The Lord of the Rings'
linter.is_likely_english("Lorem ipsum dolor sit")   # False
linter.isolate_english(text)                        # only the English parts
```

The two English-detection helpers are, as Harper says, a proof of concept.

## Threads

`lint`, `organized_lints` and `Linter()` release the GIL, so linters in different threads
run in parallel. A single `Linter` is not thread-safe: a call made while another thread is
inside a call on the same object raises `RuntimeError`. Use one `Linter` per thread.
