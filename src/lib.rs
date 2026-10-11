// The binding layer is ported from harper-wasm/src/lib.rs of Harper 2.11.0
// (https://github.com/Automattic/harper), Copyright Automattic Inc. and Harper contributors,
// licensed under the Apache License, Version 2.0. Changes: wasm-bindgen replaced by PyO3,
// spans kept in Unicode code points instead of UTF-16 code units, JSON/JsValue twins merged
// into dict-returning methods.

#![allow(clippy::too_many_arguments)] // `lint` mirrors harper.js's LintOptions

use std::collections::HashMap;
use std::io::Cursor;
use std::sync::Arc;

use harper_core::language_detection::is_doc_likely_english;
use harper_core::linting::{HumanReadableStructuredConfig, StructuredConfig};
use harper_core::linting::{LintGroup, Linter as _};
use harper_core::parsers::{IsolateEnglish, Markdown, Mask, OopsAllHeadings, Parser, PlainEnglish};
use harper_core::remove_overlaps_map;
use harper_core::weirpack::Weirpack;
use harper_core::{
    CharString, DictWordMetadata, Document, IgnoredLints, LintContext, Lrc, remove_overlaps,
    spell::{Dictionary, FstDictionary, MergedDictionary, MutableDictionary},
};
use harper_core::{DialectFlags, RegexMasker};
use harper_stats::{Record, RecordKind, Stats};
use pyo3::exceptions::{PyUserWarning, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString};
use serde::{Deserialize, Serialize};

/// `Result::Err` of harper-wasm becomes `ValueError` with the same message.
fn value_error(err: impl ToString) -> PyErr {
    PyValueError::new_err(err.to_string())
}

/// Convert a Rust value to Python through JSON, as harper-wasm's `Serializer::json_compatible`.
fn to_py<'py>(py: Python<'py>, value: &impl Serialize) -> PyResult<Bound<'py, PyAny>> {
    let json = serde_json::to_string(value).map_err(value_error)?;
    py.import("json")?.call_method1("loads", (json,))
}

/// harper-wasm's `make_serialize_fns_for!`: `to_json` / `from_json` on Lint, Suggestion, Span.
fn to_json(value: &impl Serialize) -> String {
    serde_json::to_string(value).unwrap()
}

fn from_json<T: for<'de> Deserialize<'de>>(json: &str) -> PyResult<T> {
    serde_json::from_str(json).map_err(value_error)
}

fn json_dumps(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.py()
        .import("json")?
        .call_method1("dumps", (obj,))?
        .extract()
}

/// Read a Python `str`. Lone surrogates become U+FFFD one for one, as wasm-bindgen does when
/// harper.js passes a JS string, so code point indices stay aligned with the input.
fn text_of(s: &Bound<'_, PyString>) -> PyResult<String> {
    if let Ok(text) = s.to_str() {
        return Ok(text.to_owned());
    }
    let bytes: Vec<u8> = s
        .call_method1("encode", ("utf-16-le", "surrogatepass"))?
        .extract()?;
    let units: Vec<u16> = bytes
        .as_chunks::<2>()
        .0
        .iter()
        .map(|&b| u16::from_le_bytes(b))
        .collect();
    Ok(String::from_utf16_lossy(&units))
}

fn warn(py: Python<'_>, message: &str) -> PyResult<()> {
    let message = std::ffi::CString::new(message).unwrap_or_default();
    PyErr::warn(py, &py.get_type::<PyUserWarning>(), &message, 1)
}

/// Build a member of one of the `enum.Enum` classes defined in `harper/__init__.py`.
fn py_enum<'py>(
    py: Python<'py>,
    class: &str,
    value: impl IntoPyObject<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    py.import("harper")?.getattr(class)?.call1((value,))
}

#[derive(Serialize, Deserialize, Debug, Copy, Clone)]
enum Language {
    Plain,
    Markdown,
    Typst,
}

impl Language {
    /// `toWasmLanguage` of LocalLinter.ts: an unknown language warns and falls back to Markdown.
    fn from_py(obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let py = obj.py();
        let value: Option<String> = py_enum(py, "Language", obj)
            .and_then(|member| member.getattr("value")?.extract())
            .ok();
        Ok(match value.as_deref() {
            Some("plaintext") => Language::Plain,
            Some("typst") => Language::Typst,
            Some("markdown") => Language::Markdown,
            _ => {
                warn(
                    py,
                    &format!("Unknown Harper language '{}'; using markdown.", obj.str()?),
                )?;
                Language::Markdown
            }
        })
    }

    fn create_parser(&self) -> Box<dyn Parser> {
        match self {
            Language::Plain => Box::new(PlainEnglish),
            Language::Markdown => Box::new(Markdown::default()),
            Language::Typst => Box::new(harper_typst::Typst),
        }
    }
}

#[derive(Debug, Copy, Clone, PartialEq)]
enum Dialect {
    American = 0,
    British = 1,
    Australian = 2,
    Canadian = 3,
    Indian = 4,
}

impl Dialect {
    fn from_py(obj: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        let Some(obj) = obj else {
            return Ok(Dialect::American);
        };
        let value: u8 = py_enum(obj.py(), "Dialect", obj)?
            .getattr("value")?
            .extract()?;
        Ok(match value {
            0 => Dialect::American,
            1 => Dialect::British,
            2 => Dialect::Australian,
            3 => Dialect::Canadian,
            _ => Dialect::Indian,
        })
    }
}

impl From<Dialect> for harper_core::Dialect {
    fn from(dialect: Dialect) -> Self {
        match dialect {
            Dialect::American => harper_core::Dialect::American,
            Dialect::Canadian => harper_core::Dialect::Canadian,
            Dialect::Australian => harper_core::Dialect::Australian,
            Dialect::British => harper_core::Dialect::British,
            Dialect::Indian => harper_core::Dialect::Indian,
        }
    }
}

struct Inner {
    lint_group: LintGroup,
    /// The user-supplied dictionary.
    ///
    /// To make changes affect linting, run [`Self::synchronize_lint_dict`].
    user_dictionary: MutableDictionary,
    dictionary: Arc<MergedDictionary>,
    weirpack_dictionaries: Vec<Arc<MutableDictionary>>,
    ignored_lints: IgnoredLints,
    dialect: Dialect,
    stats: Stats,
}

impl Inner {
    fn new(dialect: Dialect) -> Self {
        let dictionary = Self::construct_merged_dict(&[Arc::new(MutableDictionary::default())]);
        let lint_group = LintGroup::new_curated_empty_config(dictionary.clone(), dialect.into());

        Self {
            lint_group,
            user_dictionary: MutableDictionary::new(),
            weirpack_dictionaries: Vec::new(),
            dictionary,
            ignored_lints: IgnoredLints::default(),
            dialect,
            stats: Stats::default(),
        }
    }

    /// Update the dictionary inside [`Self::lint_group`] to include [`Self::user_dictionary`].
    /// This clears any linter caches, so use it sparingly.
    fn synchronize_lint_dict(&mut self) {
        let lint_config = self.lint_group.config.clone();

        let mut constituent_dictionaries = vec![Arc::new(self.user_dictionary.clone())];
        constituent_dictionaries.extend(self.weirpack_dictionaries.iter().cloned());

        self.dictionary = Self::construct_merged_dict(&constituent_dictionaries);

        self.lint_group =
            LintGroup::new_curated_empty_config(self.dictionary.clone(), self.dialect.into());

        self.lint_group.config.merge_from(lint_config);
    }

    /// Construct the actual dictionary to be used for linting and parsing from the curated dictionary
    /// and any other runtime-provided dictionaries.
    fn construct_merged_dict(dicts: &[Arc<impl Dictionary + 'static>]) -> Arc<MergedDictionary> {
        let mut lint_dict = MergedDictionary::new();

        lint_dict.add_dictionary(FstDictionary::curated());

        for dict in dicts {
            lint_dict.add_dictionary(Arc::new(dict.clone()));
        }

        Arc::new(lint_dict)
    }

    fn create_lint_parser(
        &self,
        language: Language,
        all_headings: bool,
        regex_mask: Option<&str>,
        isolate_english: bool,
    ) -> Option<Box<dyn Parser>> {
        let mut parser = language.create_parser();

        if let Some(regex) = regex_mask {
            let masker = RegexMasker::new(regex, true)?;
            parser = Box::new(Mask::new(masker, parser));
        }

        if all_headings {
            parser = Box::new(OopsAllHeadings::new(parser));
        }

        if isolate_english {
            parser = Box::new(IsolateEnglish::new(parser, self.dictionary.clone()));
        }

        Some(parser)
    }

    fn with_curated_config<T>(&mut self, lint: impl FnOnce(&mut LintGroup) -> T) -> T {
        let config = self.lint_group.config.clone();
        self.lint_group.config.fill_with_curated();

        let output = lint(&mut self.lint_group);

        self.lint_group.config = config;
        output
    }

    fn document(&self, source_text: &str, language: Language) -> (Lrc<[char]>, Document) {
        let source: Lrc<[char]> = source_text.chars().collect();
        let document =
            Document::new_from_chars(source.clone(), &language.create_parser(), &self.dictionary);
        (source, document)
    }

    /// `None` when the regex mask is invalid.
    fn organized_lints(
        &mut self,
        text: &str,
        opts: &LintOptions,
    ) -> Option<Vec<(String, Vec<Lint>)>> {
        let source: Lrc<[char]> = text.chars().collect();
        let parser = self.create_lint_parser(
            opts.language,
            opts.all_headings,
            opts.regex_mask.as_deref(),
            opts.isolate_english,
        )?;

        let document = Document::new_from_chars(source.clone(), &parser, &self.dictionary);

        let mut lints =
            self.with_curated_config(|lint_group| lint_group.organized_lints(&document));

        for value in lints.values_mut() {
            self.ignored_lints.remove_ignored(value, &document);
        }

        if opts.dedup {
            remove_overlaps_map(&mut lints);
        }

        Some(
            lints
                .into_iter()
                .map(|(group, ls)| {
                    let ls = ls
                        .into_iter()
                        .map(|l| Lint::new(l, &source, opts.language))
                        .collect();
                    (group, ls)
                })
                .collect(),
        )
    }

    /// `None` when the regex mask is invalid.
    fn lint(&mut self, text: &str, opts: &LintOptions) -> Option<Vec<Lint>> {
        let source: Lrc<[char]> = text.chars().collect();
        let parser = self.create_lint_parser(
            opts.language,
            opts.all_headings,
            opts.regex_mask.as_deref(),
            opts.isolate_english,
        )?;

        let document = Document::new_from_chars(source.clone(), &parser, &self.dictionary);

        let mut lints = self.with_curated_config(|lint_group| lint_group.lint(&document));

        self.ignored_lints.remove_ignored(&mut lints, &document);
        if opts.dedup {
            remove_overlaps(&mut lints);
        }

        Some(
            lints
                .into_iter()
                .map(|l| Lint::new(l, &source, opts.language))
                .collect(),
        )
    }
}

struct LintOptions {
    language: Language,
    all_headings: bool,
    regex_mask: Option<String>,
    dedup: bool,
    isolate_english: bool,
}

/// Harper's grammar checker: harper.js's `LocalLinter`, synchronous.
///
/// Construction builds the curated dictionary and is the expensive step: create one
/// `Linter` and reuse it.
///
/// The GIL is released while linting and during construction, but a `Linter` is not
/// thread-safe: a call made while another thread is inside a call on the same `Linter`
/// raises `RuntimeError`. Create one per thread to lint in parallel.
#[pyclass(module = "harper")]
struct Linter {
    inner: Inner,
}

impl Linter {
    fn lint_options(
        language: Option<&Bound<'_, PyAny>>,
        regex_mask: Option<String>,
        force_all_headings: bool,
        dedup: bool,
        isolate_english: bool,
    ) -> PyResult<LintOptions> {
        Ok(LintOptions {
            language: language.map_or(Ok(Language::Markdown), Language::from_py)?,
            all_headings: force_all_headings,
            regex_mask,
            dedup,
            isolate_english,
        })
    }

    fn warn_invalid_regex(py: Python<'_>, opts: &LintOptions) -> PyResult<()> {
        let regex = opts.regex_mask.as_deref().unwrap_or_default();
        warn(
            py,
            &format!("Ignoring lint request because the regex mask is invalid: {regex}"),
        )
    }
}

#[pymethods]
impl Linter {
    #[new]
    #[pyo3(signature = (dialect = None))]
    fn new(py: Python<'_>, dialect: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        let dialect = Dialect::from_py(dialect)?;
        let inner = py.detach(|| Inner::new(dialect));
        Ok(Self { inner })
    }

    #[pyo3(signature = (text, *, language = None, regex_mask = None, force_all_headings = false, dedup = true, isolate_english = false))]
    fn lint(
        &mut self,
        py: Python<'_>,
        text: &Bound<'_, PyString>,
        language: Option<&Bound<'_, PyAny>>,
        regex_mask: Option<String>,
        force_all_headings: bool,
        dedup: bool,
        isolate_english: bool,
    ) -> PyResult<Vec<Lint>> {
        let text = text_of(text)?;
        let opts = Self::lint_options(
            language,
            regex_mask,
            force_all_headings,
            dedup,
            isolate_english,
        )?;
        let inner = &mut self.inner;
        match py.detach(|| inner.lint(&text, &opts)) {
            Some(lints) => Ok(lints),
            None => Self::warn_invalid_regex(py, &opts).map(|_| vec![]),
        }
    }

    #[pyo3(signature = (text, *, language = None, regex_mask = None, force_all_headings = false, dedup = true, isolate_english = false))]
    fn organized_lints<'py>(
        &mut self,
        py: Python<'py>,
        text: &Bound<'py, PyString>,
        language: Option<&Bound<'py, PyAny>>,
        regex_mask: Option<String>,
        force_all_headings: bool,
        dedup: bool,
        isolate_english: bool,
    ) -> PyResult<Bound<'py, PyDict>> {
        let text = text_of(text)?;
        let opts = Self::lint_options(
            language,
            regex_mask,
            force_all_headings,
            dedup,
            isolate_english,
        )?;
        let inner = &mut self.inner;
        let output = PyDict::new(py);
        match py.detach(|| inner.organized_lints(&text, &opts)) {
            Some(groups) => {
                for (group, lints) in groups {
                    output.set_item(group, lints)?;
                }
            }
            None => Self::warn_invalid_regex(py, &opts)?,
        }
        Ok(output)
    }

    /// Apply a suggestion from a given lint.
    /// This action will be logged to the Linter's statistics.
    fn apply_suggestion(
        &mut self,
        text: &Bound<'_, PyString>,
        lint: PyRef<'_, Lint>,
        suggestion: PyRef<'_, Suggestion>,
    ) -> PyResult<String> {
        let text = text_of(text)?;
        let (source, doc) = self.inner.document(&text, lint.language);

        self.inner
            .stats
            .records
            .push(Record::now(RecordKind::from_lint(&lint.inner, &doc)));

        let mut source = source.to_vec();
        suggestion.inner.apply(lint.inner.span, &mut source);

        Ok(source.iter().collect())
    }

    fn is_likely_english(&self, text: &Bound<'_, PyString>) -> PyResult<bool> {
        let text = text_of(text)?;
        let document = Document::new_plain_english(&text, &self.inner.dictionary);
        Ok(is_doc_likely_english(&document, &self.inner.dictionary))
    }

    fn isolate_english(&self, text: &Bound<'_, PyString>) -> PyResult<String> {
        let text = text_of(text)?;
        let dictionary = &self.inner.dictionary;
        let document = Document::new(
            &text,
            &IsolateEnglish::new(Box::new(PlainEnglish), dictionary.clone()),
            dictionary,
        );

        Ok(document.to_string())
    }

    fn get_lint_config<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        to_py(py, &self.inner.lint_group.config)
    }

    fn set_lint_config(&mut self, config: &Bound<'_, PyAny>) -> PyResult<()> {
        self.inner.lint_group.config =
            serde_json::from_str(&json_dumps(config)?).map_err(value_error)?;
        Ok(())
    }

    fn get_default_lint_config<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        get_default_lint_config(py)
    }

    fn get_structured_lint_config<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let mut config = StructuredConfig::curated();
        config.copy_from_flat_config(&self.inner.lint_group.config);

        let human = HumanReadableStructuredConfig::from_structured_config(&config);
        to_py(py, &human)
    }

    fn get_lint_descriptions<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        to_py(py, &self.inner.lint_group.all_descriptions())
    }

    fn get_lint_descriptions_html<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        to_py(py, &self.inner.lint_group.all_descriptions_html())
    }

    fn to_title_case(&self, text: &Bound<'_, PyString>) -> PyResult<String> {
        to_title_case(text)
    }

    fn ignore_lint(&mut self, text: &Bound<'_, PyString>, lint: PyRef<'_, Lint>) -> PyResult<()> {
        self.ignore_lints(text, vec![lint])
    }

    fn ignore_lints(
        &mut self,
        text: &Bound<'_, PyString>,
        lints: Vec<PyRef<'_, Lint>>,
    ) -> PyResult<()> {
        let text = text_of(text)?;
        let source: Lrc<[char]> = text.chars().collect();

        for lint in lints {
            let document = Document::new_from_chars(
                source.clone(),
                &lint.language.create_parser(),
                &self.inner.dictionary,
            );

            self.inner.ignored_lints.ignore_lint(&lint.inner, &document);
        }
        Ok(())
    }

    fn ignore_lint_hash(&mut self, hash: u64) {
        self.inner.ignored_lints.ignore_hash(hash);
    }

    /// Export the linter's ignored lints as a privacy-respecting JSON list of hashes.
    fn export_ignored_lints(&self) -> String {
        serde_json::to_string(&self.inner.ignored_lints).unwrap()
    }

    /// Import into the linter's ignored lints from a privacy-respecting JSON list of hashes.
    fn import_ignored_lints(&mut self, json: &str) -> PyResult<()> {
        let list: IgnoredLints = serde_json::from_str(json).map_err(value_error)?;
        self.inner.ignored_lints.append(list);
        Ok(())
    }

    fn clear_ignored_lints(&mut self) {
        self.inner.ignored_lints = IgnoredLints::new();
    }

    /// Compute the context hash of a given lint.
    fn context_hash(&self, text: &Bound<'_, PyString>, lint: PyRef<'_, Lint>) -> PyResult<u64> {
        let text = text_of(text)?;
        let (_, document) = self.inner.document(&text, lint.language);
        Ok(LintContext::from_lint(&lint.inner, &document).default_hash())
    }

    fn clear_words(&mut self) {
        self.inner.user_dictionary = MutableDictionary::new();
        self.inner.synchronize_lint_dict();
    }

    fn import_words(&mut self, words: Vec<String>) {
        let inner = &mut self.inner;
        let init_len = inner.user_dictionary.word_count();
        let dialects = DialectFlags::from_dialect(inner.dialect.into());

        inner.user_dictionary.extend_words(words.iter().map(|word| {
            (
                word.chars().collect::<CharString>(),
                DictWordMetadata {
                    dialects,
                    ..Default::default()
                },
            )
        }));

        // Only synchronize if we added words that were not there before.
        if inner.user_dictionary.word_count() > init_len {
            inner.synchronize_lint_dict();
        }
    }

    fn export_words(&self) -> Vec<String> {
        self.inner
            .user_dictionary
            .words_iter()
            .map(|v| v.iter().collect())
            .collect()
    }

    #[getter]
    fn get_dialect<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        py_enum(py, "Dialect", self.inner.dialect as u8)
    }

    /// `LocalLinter.setDialect`: a different dialect replaces the inner linter with a new one.
    #[setter]
    fn set_dialect(&mut self, py: Python<'_>, dialect: &Bound<'_, PyAny>) -> PyResult<()> {
        let dialect = Dialect::from_py(Some(dialect))?;
        if dialect != self.inner.dialect {
            self.inner = py.detach(|| Inner::new(dialect));
        }
        Ok(())
    }

    #[pyo3(signature = (start = None, end = None))]
    fn summarize_stats<'py>(
        &self,
        py: Python<'py>,
        start: Option<i64>,
        end: Option<i64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let mut operable_copy = self.inner.stats.clone();

        if let Some(start) = start {
            operable_copy.records.retain(|i| i.when > start);
        }

        if let Some(end) = end {
            operable_copy.records.retain(|i| i.when < end);
        }

        to_py(py, &operable_copy.summarize())
    }

    fn generate_stats_file(&self) -> String {
        let mut output = Vec::new();
        self.inner.stats.write(&mut output).unwrap();
        String::from_utf8(output).unwrap()
    }

    fn import_stats_file(&mut self, text: &str) -> PyResult<()> {
        let mut read = Cursor::new(text.as_bytes());
        let mut new_stats = Stats::read(&mut read).map_err(value_error)?;
        self.inner.stats.records.append(&mut new_stats.records);
        Ok(())
    }

    /// Load a Weirpack from raw bytes, merging its rules into the current linter.
    /// Returns test failures if any are found, and does not import in that case.
    fn load_weirpack<'py>(
        &mut self,
        py: Python<'py>,
        data: &[u8],
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        #[derive(Serialize)]
        struct WeirpackTestFailure {
            expected: String,
            got: String,
        }

        let pack = Weirpack::from_bytes(data).map_err(value_error)?;
        let failures = pack.run_tests().map_err(value_error)?;

        if !failures.is_empty() {
            let mapped: HashMap<String, Vec<WeirpackTestFailure>> = failures
                .into_iter()
                .map(|(rule, results)| {
                    let failures = results
                        .into_iter()
                        .map(|result| WeirpackTestFailure {
                            expected: result.expected,
                            got: result.got,
                        })
                        .collect();
                    (rule, failures)
                })
                .collect();
            return to_py(py, &mapped).map(Some);
        }

        let inner = &mut self.inner;
        if let Some(dict) = pack.load_dictionary().map_err(value_error)? {
            inner.weirpack_dictionaries.push(Arc::new(dict));
            inner.synchronize_lint_dict();
        }

        let group = pack.to_lint_group().map_err(value_error)?;
        inner.lint_group.merge_from(group);
        Ok(None)
    }
}

#[pyfunction]
fn to_title_case(text: &Bound<'_, PyString>) -> PyResult<String> {
    let text = text_of(text)?;
    Ok(harper_core::make_title_case_str(
        &text,
        &PlainEnglish,
        &FstDictionary::curated(),
    ))
}

#[pyfunction]
fn get_default_lint_config(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let config =
        LintGroup::new_curated(MutableDictionary::new().into(), Dialect::American.into()).config;
    to_py(py, &config)
}

/// A suggestion to fix a Lint.
#[pyclass(frozen, eq, hash, module = "harper")]
#[derive(Serialize, Deserialize, PartialEq, Eq, Hash)]
struct Suggestion {
    inner: harper_core::linting::Suggestion,
}

#[pymethods]
impl Suggestion {
    fn to_json(&self) -> String {
        to_json(self)
    }

    #[staticmethod]
    fn from_json(json: &str) -> PyResult<Self> {
        from_json(json)
    }

    #[getter]
    fn kind<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        use harper_core::linting::Suggestion::*;
        let kind = match &self.inner {
            ReplaceWith(_) => 0,
            Remove => 1,
            InsertAfter(_) => 2,
        };
        py_enum(py, "SuggestionKind", kind)
    }

    /// The text that is going to replace the problematic section; empty for `REMOVE`.
    #[getter]
    fn replacement_text(&self) -> String {
        use harper_core::linting::Suggestion::*;
        match &self.inner {
            Remove => "".to_string(),
            ReplaceWith(chars) | InsertAfter(chars) => chars.iter().collect(),
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let kind = self.kind(py)?.getattr("name")?;
        let text = PyString::new(py, &self.replacement_text()).repr()?;
        Ok(format!(
            "Suggestion(kind=SuggestionKind.{kind}, replacement_text={text})"
        ))
    }
}

/// An error found in provided text.
#[pyclass(frozen, module = "harper")]
#[derive(Serialize, Deserialize)]
struct Lint {
    inner: harper_core::linting::Lint,
    span: Span,
    problem_text: String,
    language: Language,
}

impl Lint {
    fn new(lint: harper_core::linting::Lint, source: &[char], language: Language) -> Self {
        Self {
            problem_text: lint.get_str(source),
            span: Span {
                start: lint.span.start,
                end: lint.span.end,
            },
            inner: lint,
            language,
        }
    }
}

#[pymethods]
impl Lint {
    fn to_json(&self) -> String {
        to_json(self)
    }

    #[staticmethod]
    fn from_json(json: &str) -> PyResult<Self> {
        from_json(json)
    }

    #[getter]
    fn span(&self) -> Span {
        self.span
    }

    #[getter]
    fn problem_text(&self) -> &str {
        &self.problem_text
    }

    #[getter]
    fn lint_kind(&self) -> String {
        self.inner.lint_kind.to_string_key()
    }

    #[getter]
    fn lint_kind_pretty(&self) -> String {
        self.inner.lint_kind.to_string()
    }

    #[getter]
    fn message(&self) -> &str {
        &self.inner.message
    }

    #[getter]
    fn message_html(&self) -> String {
        self.inner.message_html()
    }

    #[getter]
    fn suggestions(&self) -> Vec<Suggestion> {
        self.inner
            .suggestions
            .iter()
            .map(|s| Suggestion { inner: s.clone() })
            .collect()
    }

    #[getter]
    fn suggestion_count(&self) -> usize {
        self.inner.suggestions.len()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let problem_text = PyString::new(py, &self.problem_text).repr()?;
        let message = PyString::new(py, &self.inner.message).repr()?;
        Ok(format!(
            "Lint(lint_kind='{}', span={}, problem_text={problem_text}, message={message}, suggestion_count={})",
            self.lint_kind(),
            self.span.__repr__(),
            self.suggestion_count(),
        ))
    }
}

/// Two code point indices into a `str`: a start and an end.
#[pyclass(frozen, eq, hash, skip_from_py_object, module = "harper")]
#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct Span {
    #[pyo3(get)]
    start: usize,
    #[pyo3(get)]
    end: usize,
}

#[pymethods]
impl Span {
    #[allow(clippy::wrong_self_convention)] // PyO3 methods take &self
    fn to_json(&self) -> String {
        to_json(self)
    }

    #[staticmethod]
    fn from_json(json: &str) -> PyResult<Self> {
        from_json(json)
    }

    #[new]
    fn new(start: usize, end: usize) -> Self {
        Self { start, end }
    }

    fn len(&self) -> usize {
        harper_core::Span::<char>::new(self.start, self.end).len()
    }

    fn is_empty(&self) -> bool {
        self.len() == 0
    }

    fn __repr__(&self) -> String {
        format!("Span(start={}, end={})", self.start, self.end)
    }
}

#[pymodule]
fn _harper(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Linter>()?;
    m.add_class::<Lint>()?;
    m.add_class::<Suggestion>()?;
    m.add_class::<Span>()?;
    m.add_function(wrap_pyfunction!(to_title_case, m)?)?;
    m.add_function(wrap_pyfunction!(get_default_lint_config, m)?)?;
    Ok(())
}
