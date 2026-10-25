# Changelog

## 0.2.0 (2026-10-25)

- Harper inside is 2.13.0 (`harper-core`, `harper-stats`, `harper-typst`), up from 2.11.0.
  harper-wasm's binding layer and harper.js's `Linter` are unchanged between the two, so the
  API is the same; parity with `harper-cli` 2.13.0 holds on the same 52 documents.

## 0.1.1 (2026-10-13)

- Python 3.15 is tested in CI and listed in the classifiers. The 0.1.0 abi3 wheels already
  run on it; this release only updates the metadata.

## 0.1.0 (2026-10-11)

First release: bindings for Harper 2.11.0 mirroring harper.js's `Linter` interface.

- `to_json()` / `from_json()` on `Lint`, `Suggestion` and `Span`, as in harper-wasm (spans in
  code points).
