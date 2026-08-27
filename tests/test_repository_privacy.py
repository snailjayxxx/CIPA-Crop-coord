from __future__ import annotations

import re
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent


def test_tests_do_not_contain_local_machine_paths_or_identifier_like_numbers() -> None:
    """Regression guard: repository tests must use synthetic fixture names only."""
    forbidden_patterns = {
        "Windows absolute path": re.compile(r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/]"),
        "Unix user home path": re.compile(r"/(?:Users|home)/[^/\s\"']+"),
        "UNC network path": re.compile(r"\\\\[^\\\s]+\\[^\\\s]+"),
        "long identifier-like number": re.compile(r"\d{10,}"),
    }

    violations: list[str] = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in forbidden_patterns.items():
            match = pattern.search(text)
            if match:
                violations.append(f"{path.name}: {label}: {match.group(0)!r}")

    assert not violations, (
        "Tests must contain only synthetic data; remove local paths, real filenames, "
        "person/project names, and machine-specific identifiers.\n" + "\n".join(violations)
    )
