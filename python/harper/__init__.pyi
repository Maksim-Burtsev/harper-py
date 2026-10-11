"""Python bindings for Harper, the offline English grammar checker.

The API mirrors harper.js's ``Linter`` interface, synchronous and snake_case.
Every difference from harper.js is listed in DEVIATIONS.md.
"""

import enum
from typing import Any, final

__all__ = [
    "Dialect",
    "Language",
    "Lint",
    "Linter",
    "Span",
    "Suggestion",
    "SuggestionKind",
    "get_default_lint_config",
    "to_title_case",
]

class Dialect(enum.IntEnum):
    """An English dialect. Values match harper.js's ``Dialect``."""

    AMERICAN = 0
    BRITISH = 1
    AUSTRALIAN = 2
    CANADIAN = 3
    INDIAN = 4

class Language(str, enum.Enum):
    """The markup language of the text. Values match harper.js's ``LintOptions.language``."""

    PLAINTEXT = "plaintext"
    MARKDOWN = "markdown"
    TYPST = "typst"

class SuggestionKind(enum.IntEnum):
    """The variant of a suggestion. Values match harper.js's ``SuggestionKind``."""

    REPLACE = 0
    """Replace the problematic text."""
    REMOVE = 1
    """Remove the problematic text."""
    INSERT_AFTER = 2
    """Insert additional text after the error."""

@final
class Span:
    """Two code point indices into a ``str``: ``text[span.start:span.end]``."""

    def __new__(cls, start: int, end: int) -> Span: ...
    @property
    def start(self) -> int: ...
    @property
    def end(self) -> int: ...
    def len(self) -> int:
        """The number of code points the span covers."""
    def is_empty(self) -> bool:
        """Whether the span covers no code points."""
    def to_json(self) -> str:
        """Serialize to JSON, as harper-wasm's ``to_json`` (spans in code points)."""
    @staticmethod
    def from_json(json: str) -> Span:
        """Rebuild from :meth:`to_json` output. Raises ``ValueError`` if it is malformed."""
    def __eq__(self, value: object, /) -> bool: ...
    def __hash__(self) -> int: ...

@final
class Suggestion:
    """A suggestion to fix a :class:`Lint`. Pass it to :meth:`Linter.apply_suggestion`."""

    @property
    def kind(self) -> SuggestionKind:
        """Whether the suggestion replaces, removes, or inserts after the problematic text."""
    @property
    def replacement_text(self) -> str:
        """The text that is going to replace the problematic section; empty for ``REMOVE``."""
    def to_json(self) -> str:
        """Serialize to JSON, as harper-wasm's ``to_json`` (spans in code points)."""
    @staticmethod
    def from_json(json: str) -> Suggestion:
        """Rebuild from :meth:`to_json` output. Raises ``ValueError`` if it is malformed."""
    def __eq__(self, value: object, /) -> bool: ...
    def __hash__(self) -> int: ...

@final
class Lint:
    """An error found in provided text.

    May include zero or more suggestions that may fix the problematic text.
    """

    @property
    def span(self) -> Span:
        """The location of the problematic text, in code points of the linted ``str``."""
    @property
    def problem_text(self) -> str:
        """The problematic text; always ``text[span.start:span.end]``."""
    @property
    def lint_kind(self) -> str:
        """The general category of the lint, as a key such as ``"WordChoice"``."""
    @property
    def lint_kind_pretty(self) -> str:
        """The general category of the lint, human-readable, such as ``"Word Choice"``."""
    @property
    def message(self) -> str:
        """A description of the error."""
    @property
    def message_html(self) -> str:
        """A description of the error as HTML."""
    @property
    def suggestions(self) -> list[Suggestion]:
        """Any suggestions that may resolve the issue."""
    @property
    def suggestion_count(self) -> int:
        """Equivalent to ``len(lint.suggestions)``."""
    def to_json(self) -> str:
        """Serialize to JSON, as harper-wasm's ``to_json`` (spans in code points).

        A lint rebuilt with :meth:`from_json` works with every ``Linter`` method that
        takes a lint, in this or another process."""
    @staticmethod
    def from_json(json: str) -> Lint:
        """Rebuild from :meth:`to_json` output. Raises ``ValueError`` if it is malformed."""

@final
class Linter:
    """Harper's grammar checker: harper.js's ``LocalLinter``, synchronous.

    Construction builds the curated dictionary and is the expensive step (about a
    second): create one ``Linter`` and reuse it.

    The GIL is released while linting and during construction, but a ``Linter`` is
    not thread-safe: a call made while another thread is inside a call on the same
    ``Linter`` raises ``RuntimeError``. Create one per thread to lint in parallel.
    """

    def __new__(cls, dialect: Dialect | int = ...) -> Linter:
        """Create a linter for the given English dialect, American by default."""
    @property
    def dialect(self) -> Dialect:
        """The dialect of English this linter was constructed for.

        Setting a different dialect replaces the linter with a new one, as harper.js's
        ``setDialect`` does: added words, ignored lints, lint config, loaded Weirpacks
        and statistics are all reset. Setting the same dialect does nothing.
        """
    @dialect.setter
    def dialect(self, dialect: Dialect) -> None: ...
    def lint(
        self,
        text: str,
        *,
        language: Language | str = ...,
        regex_mask: str | None = None,
        force_all_headings: bool = False,
        dedup: bool = True,
        isolate_english: bool = False,
    ) -> list[Lint]:
        """Lint the provided text.

        Args:
            text: The text to check.
            language: The markup language of ``text``, Markdown by default; harper.js's
                strings (``"plaintext"``, ...) work too. An unknown value warns and
                falls back to Markdown, as harper.js does.
            regex_mask: Text matching this regular expression is not linted. If it
                cannot be parsed, a warning is issued and ``[]`` is returned.
            force_all_headings: Treat the whole document as headings.
            dedup: Remove overlapping lints.
            isolate_english: Ignore text that is unlikely to be English.
        """
    def organized_lints(
        self,
        text: str,
        *,
        language: Language | str = ...,
        regex_mask: str | None = None,
        force_all_headings: bool = False,
        dedup: bool = True,
        isolate_english: bool = False,
    ) -> dict[str, list[Lint]]:
        """Lint the provided text, keyed by the name of the rule that produced each lint.

        Every rule has a key, with an empty list when it found nothing. Options are as
        in :meth:`lint`.
        """
    def apply_suggestion(self, text: str, lint: Lint, suggestion: Suggestion) -> str:
        """Apply a suggestion from a lint to text, returning the changed text.

        The action is recorded in the linter's statistics.
        """
    def is_likely_english(self, text: str) -> bool:
        """Determine if the provided text is likely to be intended to be English.

        The algorithm is a proof of concept and does not work terribly well.
        """
    def isolate_english(self, text: str) -> str:
        """Return the parts of a string that are likely intended to be English.

        The algorithm is a proof of concept and does not work terribly well.
        """
    def get_lint_config(self) -> dict[str, bool | None]:
        """The linter's current configuration: rule name to on, off, or ``None`` (default)."""
    def set_lint_config(self, config: dict[str, bool | None]) -> None:
        """Replace the linter's configuration. Raises ``ValueError`` if it is malformed."""
    def get_default_lint_config(self) -> dict[str, bool]:
        """The default configuration. Does not read or change this linter's configuration."""
    def get_structured_lint_config(self) -> dict[str, Any]:
        """The current configuration organized for settings UIs (``{"settings": [...]}``).

        Changes must still be applied through :meth:`set_lint_config`.
        """
    def get_lint_descriptions(self) -> dict[str, str]:
        """The description of every rule, in Markdown."""
    def get_lint_descriptions_html(self) -> dict[str, str]:
        """The description of every rule, in HTML."""
    def to_title_case(self, text: str) -> str:
        """Convert a string to Chicago-style title case."""
    def ignore_lint(self, text: str, lint: Lint) -> None:
        """Ignore future instances of a lint from a previous linting run of ``text``."""
    def ignore_lints(self, text: str, lints: list[Lint]) -> None:
        """Ignore future instances of lints from a previous linting run of ``text``."""
    def ignore_lint_hash(self, hash: int) -> None:
        """Ignore future instances of a lint by its :meth:`context_hash`."""
    def export_ignored_lints(self) -> str:
        """Export the ignored lints as a JSON list of privacy-respecting hashes."""
    def import_ignored_lints(self, json: str) -> None:
        """Append ignored lints from :meth:`export_ignored_lints` output.

        Raises ``ValueError`` if the JSON is malformed.
        """
    def clear_ignored_lints(self) -> None:
        """Forget all previously ignored lints."""
    def context_hash(self, text: str, lint: Lint) -> int:
        """A context-sensitive hash that identifies a lint in ``text``."""
    def clear_words(self) -> None:
        """Remove the words added with :meth:`import_words`. The curated dictionary stays."""
    def import_words(self, words: list[str]) -> None:
        """Add words to the dictionary. This is a significant operation: batch words."""
    def export_words(self) -> list[str]:
        """The words added with :meth:`import_words` (not the curated dictionary)."""
    def summarize_stats(self, start: int | None = None, end: int | None = None) -> dict[str, Any]:
        """Summarize the linter's usage statistics.

        ``start`` and ``end`` are Unix timestamps in seconds; only records strictly after
        ``start`` and strictly before ``end`` count. The result has ``lint_counts``,
        ``total_applied``, ``final_config`` and ``misspelled``.
        """
    def generate_stats_file(self) -> str:
        """The statistics log, to save to permanent storage."""
    def import_stats_file(self, text: str) -> None:
        """Append records from :meth:`generate_stats_file` output.

        Raises ``ValueError`` if the file is malformed.
        """
    def load_weirpack(self, data: bytes) -> dict[str, list[dict[str, str]]] | None:
        """Load a Weirpack (a zip of Weir rules and dictionary) and merge its rules in.

        Returns ``None`` when the pack's tests pass and its rules are imported. Otherwise
        nothing is imported and the failing tests are returned as
        ``{rule: [{"expected": ..., "got": ...}]}``. Raises ``ValueError`` if the pack
        cannot be read.
        """

def to_title_case(text: str) -> str:
    """Convert a string to Chicago-style title case."""

def get_default_lint_config() -> dict[str, bool]:
    """The default lint configuration: every rule name to whether it is on by default."""
