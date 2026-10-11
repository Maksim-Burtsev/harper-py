# harper-py

[![PyPI](https://img.shields.io/pypi/v/harper-py.svg)](https://pypi.org/project/harper-py/)
[![Python versions](https://img.shields.io/pypi/pyversions/harper-py.svg)](https://pypi.org/project/harper-py/)
[![CI](https://github.com/Maksim-Burtsev/harper-py/actions/workflows/wheels.yml/badge.svg)](https://github.com/Maksim-Burtsev/harper-py/actions/workflows/wheels.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/Maksim-Burtsev/harper-py/blob/main/LICENSE)

Python bindings for [Harper](https://github.com/Automattic/harper), Automattic's offline
English grammar checker written in Rust: grammar, spelling and style in milliseconds, in
process, with no Java and no server. Unofficial; the API is the official harper.js one,
in snake_case.

```bash
pip install harper-py
```

```python
from harper import Linter

linter = Linter()  # build once and reuse: construction loads the dictionary
text = "This is an test of the the linter."
for lint in linter.lint(text):
    print(f"{lint.span.start}: {lint.problem_text!r} {lint.message}")
    print("   ", linter.apply_suggestion(text, lint, lint.suggestions[0]))
```

```text
8: 'an' Incorrect indefinite article.
    This is a test of the the linter.
19: 'the the' Did you mean to repeat this word?
    This is an test of the linter.
```

Spans are `str` indices, so `text[lint.span.start:lint.span.end]` is always the flagged
text, emoji included. Markdown (the default), plain text and Typst are understood;
dialects, rule configuration, a user dictionary, ignored lints and Weirpacks work as in
harper.js. The [guide](https://github.com/Maksim-Burtsev/harper-py/blob/main/docs/guide.md)
has the tour.

## Why not language-tool-python

| | harper-py | [language-tool-python](https://github.com/jxmorris12/language_tool_python) |
| --- | --- | --- |
| Runtime | none, the wheel is self-contained | [Java ≥ 17](https://github.com/jxmorris12/language_tool_python#requirements) and a local LanguageTool server it starts |
| Download | 9.7–10.4 MB wheel, depending on the platform | a 60 kB wheel, then the [LanguageTool 6.8 zip](https://github.com/jxmorris12/language_tool_python/releases/tag/LanguageTool-6.8) (259 MB) on first use |
| Cold start | 0.23 s: `import harper` + `Linter()` in a fresh process | starts a JVM server (not measured: no Java on this machine) |
| Lint 1007 words | 23 ms (first call in a process: 95 ms) | — |

Measured on an Apple M4 Mac mini, CPython 3.11, with `benchmarks/bench.py`. LanguageTool
has far more rules and languages; Harper is the choice when you want English checking that
starts fast and ships as a plain dependency.

## Platforms

Wheels for Linux (glibc and musl; x86_64, aarch64), macOS (arm64, x86_64) and Windows
(x64, arm64); one abi3 wheel per platform covers CPython 3.10 and later. Building the sdist
needs a Rust toolchain.

## Same as harper.js

`Linter` is harper.js's `Linter` interface, synchronous: `organizedLints` →
`organized_lints`, `getLintConfig` → `get_lint_config`, `LintOptions` → keyword
arguments. Harper inside is **2.11.0** (`harper-core`, `harper-stats`, `harper-typst`
from crates.io), with harper-wasm's features. Lints are checked against `harper-cli` of
the same version on a 52-document corpus, and harper.js's own test suite is ported.
Every difference is listed in
[DEVIATIONS.md](https://github.com/Maksim-Burtsev/harper-py/blob/main/DEVIATIONS.md).

## License

Apache-2.0, like Harper. The binding layer is ported from Harper's harper-wasm.
