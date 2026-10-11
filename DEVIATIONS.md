# Deviations from harper.js

The linting is Harper 2.11.0's, untouched: the binding layer is harper-wasm's `lib.rs` ported
from wasm-bindgen to PyO3, and the same text gives the same lints, messages and suggestions
(checked against `harper-cli` 2.11.0 in `tests/parity`). What follows is everything a
harper.js user would notice in Python.

## 1. Spans are `str` indices

harper.js reports spans in UTF-16 code units, the unit of JS string indices. Here they are
Unicode code points, the unit of Python `str` indices, so
`text[lint.span.start:lint.span.end] == lint.problem_text` for any text, emoji included.
Harper counts in code points internally, so these are its own indices: harper-wasm's
conversion to UTF-16 is simply not done. `"✉️👋 sdssda"`-style text gives different numbers
than harper.js (44..50 here where harper.js says 48..54 in the ported test) for the same
words.

A Python `str` can hold a lone surrogate, which is not valid Unicode. It becomes U+FFFD
on the way in, one for one, which is what wasm-bindgen does to a JS string with a lone
surrogate: indices still line up with the input, but `problem_text` and the text returned
by `apply_suggestion` carry U+FFFD where the input had the surrogate.

The same goes for the JSON of `Lint.to_json()` / `Span.to_json()` (section 5): its `span`
is in code points, where harper.js writes UTF-16 code units. For text with characters
outside the Basic Multilingual Plane (most emoji), JSON from harper.js and from harper-py
therefore carry different outer `span` numbers for the same lint. The lint's position
inside `inner`, which is what `apply_suggestion`, `ignore_lint` and `context_hash` use, is
in code points in both.

## 2. Synchronous, no JS runtime plumbing

Every method returns its result instead of a `Promise`. There is no `setup()` (the
construction does the work), no `dispose()` (memory is freed with the object), and no
`loadWeirpackFromBlob` (`load_weirpack(bytes)` is `loadWeirpackFromBytes`). `LocalLinter`
and `WorkerLinter` are one class, `Linter`; `BinaryModule`, `createBinaryModuleFromUrl`
and the `free()` methods of the wasm objects have no counterpart. harper.js's
`packWeirpackFiles` / `unpackWeirpackBytes` zip helpers are not bound: a Weirpack is a zip
archive, which `zipfile` reads and writes.

Where harper.js writes to the console, Python issues a `UserWarning` with the same text:
an invalid `regex_mask` ("Ignoring lint request because the regex mask is invalid: …",
then `[]` / `{}` is returned as in harper.js) and an unknown `language` ("Unknown Harper
language '…'; using markdown.", then Markdown is used as in harper.js). These are the only
console messages harper.js prints; Harper's crates log nothing.

## 3. Dicts instead of the JSON twins

Methods take and return dicts; `json.dumps` gives the JSON form. Dropped:
`getLintConfigAsJSON`, `setLintConfigWithJSON`, `getDefaultLintConfigAsJSON`,
`getStructuredLintConfigJSON`, `getLintDescriptionsAsJSON`,
`getLintDescriptionsHTMLAsJSON`. Ignored lints (`export_ignored_lints` /
`import_ignored_lints`) and statistics files (`generate_stats_file` / `import_stats_file`)
stay strings: they are file formats to store.

`set_lint_config` serializes the dict with `json.dumps` and parses it with serde_json, where
harper-wasm parses the JS object with serde-wasm-bindgen. Values `json.dumps` cannot encode
raise its `TypeError`; a dict of the wrong shape raises `ValueError` with serde_json's
message, which is worded differently from serde-wasm-bindgen's.

## 4. `dialect` is a property

`getDialect()` / `setDialect(d)` are `linter.dialect` / `linter.dialect = d`. Setting a
different dialect replaces the inner linter with a new one, as `LocalLinter.setDialect`
does, so added words, ignored lints, the lint config, loaded Weirpacks and statistics are
reset; setting the current dialect does nothing.

## 5. Names and types

- Methods are snake_case: `organizedLints` → `organized_lints`, `ignoreLintHash` →
  `ignore_lint_hash`, `loadWeirpackFromBytes` → `load_weirpack`, and so on. `LintOptions`
  become keyword-only arguments: `language`, `regex_mask`, `force_all_headings`, `dedup`,
  `isolate_english`, with harper.js's defaults. The `LinterInit` object becomes
  `Linter(dialect=...)`.
- `Lint`, `Suggestion` and `Span` getters are attributes: `lint.span()` → `lint.span`,
  `get_problem_text()` → `problem_text`, `lint_kind()` → `lint_kind`, `suggestions()` →
  `suggestions`, `get_replacement_text()` → `replacement_text`, `kind()` → `kind`.
  `Span.new(start, end)` is `Span(start, end)`. `Span` and `Suggestion` are immutable,
  compare and hash by value, and have a readable `repr`; so does `Lint`, which compares by
  identity.
- `to_json()` and the static `from_json(json)` exist on `Lint`, `Suggestion` and `Span`, as
  harper-wasm's `make_serialize_fns_for!` defines them, with the same serde fields; a lint
  rebuilt with `from_json` works with every `Linter` method that takes one. `from_json`
  raises `ValueError` with serde's message where harper.js throws it. Span units differ
  (section 1). There is no pickling, as harper.js has none.
- `Dialect` and `SuggestionKind` are `enum.IntEnum`s with harper-wasm's numeric values.
  `Language` is a `str` enum whose values are harper.js's strings, so
  `language="plaintext"` works as in harper.js.
- Context hashes (`context_hash`, `ignore_lint_hash`) are Python ints where harper.js has
  `bigint`; `summarize_stats(start, end)` takes ints (Unix seconds) where harper.js takes
  `bigint`s.
- `summarize_stats` returns everything harper-stats' `Summary` serializes:
  `lint_counts`, `total_applied`, `misspelled` and also `final_config`, which the object
  harper.js returns at run time contains although its TypeScript `Summary` type does not
  declare it.
- `get_default_lint_config` and `to_title_case` are module functions (harper.js has them on
  `BinaryModule`) and `Linter` methods (as on harper.js's `Linter`).

## 6. Errors

A `Result::Err` of harper-wasm (a malformed config, ignored-lints JSON, stats file or
Weirpack, or `from_json` input) raises `ValueError` with the upstream message; in harper.js
it is a thrown string.

## 7. Threads

JS has no shared-memory threads; Python does. The GIL is released while linting and while
constructing a `Linter`, so linters in different threads run in parallel. One `Linter` is
not thread-safe: it can be used from any thread, but a call made while another thread is
inside a call on the same `Linter` raises `RuntimeError("Already borrowed")` instead of
waiting. (PyO3's `unsendable` alternative would forbid other threads altogether and fail
there with a Rust panic, `PanicException`, which is a `BaseException`.)
