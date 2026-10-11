"""Numbers quoted in the README.

essay.md is the first 1007 words of Harper's harper-core/benches/essay.md (Apache-2.0).

    python benchmarks/bench.py
"""

import pathlib
import statistics
import subprocess
import sys
import time

ESSAY = (pathlib.Path(__file__).parent / "essay.md").read_text("utf-8")

COLD = """
import time
t = time.perf_counter()
import harper
linter = harper.Linter()
t1 = time.perf_counter()
linter.lint(open({path!r}, encoding="utf-8").read())
t2 = time.perf_counter()
print(t1 - t, t2 - t1)
"""


def main() -> None:
    cold = [
        tuple(map(float, subprocess.check_output(
            [sys.executable, "-c", COLD.format(path=str(pathlib.Path(__file__).parent / "essay.md"))]
        ).split()))
        for _ in range(5)
    ]
    print(f"import + Linter(), fresh process:  {min(c[0] for c in cold) * 1000:.0f} ms (best of 5)")
    print(f"first lint of the essay:           {min(c[1] for c in cold) * 1000:.0f} ms (best of 5)")

    import harper

    linter = harper.Linter()
    linter.lint(ESSAY)
    runs = []
    for _ in range(20):
        t = time.perf_counter()
        linter.lint(ESSAY)
        runs.append(time.perf_counter() - t)
    words = len(ESSAY.split())
    print(f"lint {words} words, warm:           {statistics.median(runs) * 1000:.0f} ms (median of 20)")


if __name__ == "__main__":
    main()
