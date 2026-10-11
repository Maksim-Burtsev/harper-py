"""The README example runs and prints what the README says."""

import contextlib
import io
import pathlib
import re

README = (pathlib.Path(__file__).parents[1] / "README.md").read_text("utf-8")


def test_readme_example():
    code, expected = re.search(r"```python\n(.*?)```\n\n```text\n(.*?)```", README, re.S).groups()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(code, {})
    assert out.getvalue() == expected
