"""Python bindings for Harper, the offline English grammar checker."""

import enum


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
    REMOVE = 1
    INSERT_AFTER = 2


from harper._harper import Lint, Linter, Span, Suggestion, get_default_lint_config, to_title_case  # noqa: E402

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
