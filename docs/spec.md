# harper-py spec

Python bindings for [Harper](https://github.com/Automattic/harper), the offline English grammar checker (Rust).
The public API mirrors the official JavaScript package `harper.js` (its `Linter` interface in
`packages/harper.js/src/Linter.ts` and the wasm layer in `harper-wasm/src/lib.rs`), made synchronous and snake_case.
Every difference from harper.js is listed in `DEVIATIONS.md`. A behaviour fork not covered here: do what harper.js does.

## Package

- PyPI name `harper-py`, import name `harper`. Own versioning from `0.1.0`.
- Rust: PyO3 (abi3, Python >= 3.10) + maturin, mixed layout (`python/harper/__init__.py`, `_harper` extension, `__init__.pyi`, `py.typed`).
- Upstream: `harper-core`, `harper-stats`, `harper-typst` pinned `=2.11.0` from crates.io (the latest version published there; the GitHub tag v2.12.0 is not on crates.io). Same features as harper-wasm defaults: `typst`, `thesaurus`. The README states the pinned Harper version.
- License Apache-2.0 (same as upstream), copyright notice for Automattic's code where copied (the binding layer is ported from harper-wasm).

## API (Python names → harper.js names)

```python
from harper import Linter, Dialect, Language, Lint, Suggestion, SuggestionKind, Span, to_title_case, get_default_lint_config

linter = Linter(dialect=Dialect.AMERICAN)          # LinterInit.dialect, default American
linter.lint(text, *, language=Language.MARKDOWN, regex_mask=None,
            force_all_headings=False, dedup=True, isolate_english=False) -> list[Lint]   # LintOptions defaults as in harper.js
linter.organized_lints(text, **same options) -> dict[str, list[Lint]]
linter.apply_suggestion(text, lint, suggestion) -> str
linter.is_likely_english(text) -> bool
linter.isolate_english(text) -> str
linter.get_lint_config() -> dict[str, bool | None]
linter.set_lint_config(config: dict[str, bool | None]) -> None
linter.get_default_lint_config() -> dict           # also module-level get_default_lint_config()
linter.get_structured_lint_config() -> dict
linter.get_lint_descriptions() -> dict[str, str]   # Markdown
linter.get_lint_descriptions_html() -> dict[str, str]
linter.to_title_case(text) -> str                  # also module-level to_title_case()
linter.ignore_lint(text, lint) / ignore_lints(text, lints) / ignore_lint_hash(hash: int)
linter.export_ignored_lints() -> str (JSON) / import_ignored_lints(json: str) / clear_ignored_lints()
linter.context_hash(text, lint) -> int
linter.clear_words() / import_words(words: list[str]) / export_words() -> list[str]
linter.dialect (property, get + set; setting a different dialect rebuilds the inner linter like LocalLinter.setDialect, keeping what harper.js keeps)
linter.summarize_stats(start: int | None = None, end: int | None = None) -> dict   # Summary shape
linter.generate_stats_file() -> str / import_stats_file(text: str)
linter.load_weirpack(data: bytes) -> dict[str, list[dict]] | None   # loadWeirpackFromBytes
```

- `Dialect`, `Language` (`PLAINTEXT`, `MARKDOWN`, `TYPST`), `SuggestionKind` (`REPLACE`, `REMOVE`, `INSERT_AFTER`) are Python enums.
- `Lint`: `span: Span`, `problem_text`, `lint_kind` (key string), `lint_kind_pretty`, `message`, `message_html`, `suggestions: list[Suggestion]`, `suggestion_count`; readable `__repr__`.
- `Suggestion`: `kind`, `replacement_text`; `Span`: `start`, `end`, `len()`, `is_empty()`; frozen, `__eq__`, `__repr__`.
- Errors that are `Result::Err` in harper-wasm raise `ValueError` with the upstream message (invalid JSON config, bad weirpack, bad stats file). An invalid `regex_mask` returns `[]` like harper.js.

## Deviations already decided (write them into DEVIATIONS.md)

1. Spans are Python `str` indices (Unicode code points), not UTF-16 code units: `text[lint.span.start:lint.span.end] == lint.problem_text` must hold for any text, emoji included.
2. Synchronous; no `setup()`, `dispose()`, `loadWeirpackFromBlob` (JS runtime concerns).
3. The `*AsJSON` / `*WithJSON` twins are dropped: Python methods take and return dicts (`json.dumps` covers the JSON form). Ignored lints and stats files stay strings, as they are file formats.
4. `getDialect`/`setDialect` become the `dialect` property.

## Behaviour

- The GIL is released around `lint`, `organized_lints` and construction. `Linter` is not thread-safe across threads (`unsendable` is fine) — say so in the docstring.
- Construction is the expensive step (curated dictionary); document "reuse one Linter".

## Tests (pytest)

- Port harper.js `Linter.test.ts` cases that apply to a sync API, 1:1 where possible.
- Golden parity: a corpus of ~50 sentences/markdown snippets (incl. emoji, CJK, Typst) linted by this package vs. the harper-cli of the same pinned version (`harper-cli lint --format json` or equivalent) — same rules, same spans after index conversion, same suggestions. Commit the corpus and the expected JSON; a script regenerates it.
- Span invariant test on random Unicode strings (hypothesis or a seeded loop).

## CI / release

- GitHub Actions: test on Linux/macOS/Windows; wheels via `PyO3/maturin-action` for manylinux x86_64 + aarch64, musllinux x86_64 + aarch64, macOS x86_64 + arm64, Windows x64 + arm64, plus sdist; run the test suite against built wheels where the runner can.
- Release on tag `v*` via PyPI trusted publishing (environment `pypi`, workflow `release.yml`) with attestations. Do not tag before the owner says the trusted publisher exists.

## Discoverability (release day)

- summary: `Python bindings for Harper, the fast offline English grammar checker written in Rust — no Java, no server`
- keywords: grammar, grammar checker, spell checker, spelling, proofreading, english, linter, prose, writing, languagetool alternative, harper, rust
- classifiers incl. `Programming Language :: Rust`, `Topic :: Text Processing :: Linguistic`, `Typing :: Typed`, `Development Status :: 3 - Alpha`
- project_urls: Documentation, Source, Changelog, Issues (exact labels)
- README (short, lunasvg-style): one line what/why → `pip install harper-py` → 8-line runnable example → "Why not language-tool-python" table (no Java ≥17, no server download, wheel size, cold start and lint time measured on this machine) → platforms → link to Harper. Longer tour in `docs/guide.md`.
- `context7.json` with `excludeFolders` for target/ and tests/ and short `rules`.
