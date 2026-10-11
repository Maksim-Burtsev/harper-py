"""Regenerate expected.json from harper-cli of the pinned Harper version.

    cargo build --release -p harper-cli   # in a checkout of Harper's v2.11.0 tag
    python tests/parity/regen.py path/to/harper-cli
"""

import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
EXTENSION = {"plaintext": "txt", "markdown": "md", "typst": "typ"}


def main(cli: str) -> None:
    corpus = json.loads((HERE / "corpus.json").read_text("utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        docs = root / "corpus"
        docs.mkdir()
        for i, case in enumerate(corpus):
            (docs / f"{i:02d}.{EXTENSION[case['language']]}").write_bytes(case["text"].encode())
        # A user and a file dictionary that do not exist, so local dictionaries cannot leak in.
        out = subprocess.run(
            [cli, "--no-color", "lint", "--format", "json", "-u", root / "none.txt", "-f", root / "none", docs],
            capture_output=True,
            check=False,
        )
    results = json.loads(out.stdout)
    # line, column and priority are not part of harper.js's Lint, so they are not compared.
    keep = ("rule", "kind", "span", "message", "suggestions", "matched_text")
    expected = [{"file": r["file"], "lints": [{k: l[k] for k in keep} for l in r["lints"]]} for r in results]
    (HERE / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"{len(expected)} documents, {sum(len(r['lints']) for r in expected)} lints")


if __name__ == "__main__":
    main(sys.argv[1])
