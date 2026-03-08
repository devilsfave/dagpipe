#!/usr/bin/env python3
"""DagPipe Documentation and Code Staleness Scanner.

Scans the repo for known stale strings — retired model names, deprecated APIs,
outdated version references. Add to RETIRED_MODELS when a provider retires a model.
CI fails if any forbidden strings are found.

Usage:
    python scripts/check_staleness.py           # scan entire repo
    python scripts/check_staleness.py src/      # scan specific directory
"""
from __future__ import annotations

import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — Update these lists when providers make changes
# ─────────────────────────────────────────────────────────────────────────────

# Model strings that are confirmed retired and must not appear in any file.
# Format: ("model_string", "replacement", "retired_date")
RETIRED_MODELS = [
    ("gemini-2.0-flash-exp", "gemini-2.5-flash", "2026-03-03"),
    ("gemini-2.0-flash", "gemini-2.5-flash", "2026-03-03"),
    ("gemini-1.5-flash", "gemini-2.5-flash", "2025-09-01"),
    ("gemini-1.5-pro", "gemini-2.5-pro", "2025-09-01"),
    ("llama3-70b-8192", "llama-3.3-70b-versatile", "2025-06-01"),
    ("llama3-8b-8192", "llama-3.1-8b-instant", "2025-06-01"),
]

# Deprecated API calls that must not appear in user-facing files
DEPRECATED_APIS = [
    ("checkpoint_dir=", "checkpoint_backend=FilesystemCheckpoint(path)", "0.2.0"),
    ("groq_rpm_limit=", "rpm_limit=", "0.1.5"),
]

# Outdated references that confuse users
OUTDATED_REFERENCES = [
    ("GPT-4\"", "GPT-4o or GPT-5", "2026-02"),
    ("GPT-4 ", "GPT-4o or GPT-5", "2026-02"),
    ("gpt-4\"", "gpt-4o or gpt-5", "2026-02"),
]

# File extensions to scan
SCAN_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".txt", ".rst"}

# Paths to always skip (never scan these)
SKIP_PATHS = {
    ".git", ".venv", ".dagpipe", "__pycache__", "node_modules",
    "dist", "build", "dagpipe_core.egg-info", "LATEST_V2_FILES",
    "check_staleness.py",          # Skip this file itself
    "CHANGELOG.md",                # Changelog may reference old names historically
    "MIGRATION.md",                # Migration guide must reference old names
    "_v1_backup",                  # Skip legacy V1 files
}

# ─────────────────────────────────────────────────────────────────────────────

def should_skip(path: Path) -> bool:
    return any(skip in path.parts for skip in SKIP_PATHS)


def scan_file(path: Path, forbidden: list[tuple]) -> list[str]:
    """Return list of violation messages for a single file."""
    violations = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    for line_num, line in enumerate(content.splitlines(), 1):
        for pattern, replacement, since in forbidden:
            if pattern in line:
                violations.append(
                    f"  {path}:{line_num} — found '{pattern}'\n"
                    f"    Replace with: '{replacement}' (since {since})\n"
                    f"    Line: {line.strip()}"
                )
    return violations


def main(scan_root: Path = Path(".")) -> int:
    all_forbidden = (
        [(m[0], m[1], m[2]) for m in RETIRED_MODELS] +
        [(d[0], d[1], d[2]) for d in DEPRECATED_APIS] +
        [(o[0], o[1], o[2]) for o in OUTDATED_REFERENCES]
    )

    all_violations = []
    files_scanned = 0

    for path in scan_root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue

        files_scanned += 1
        violations = scan_file(path, all_forbidden)
        all_violations.extend(violations)

    print(f"Scanned {files_scanned} files.")

    if all_violations:
        print(f"\n❌ STALENESS VIOLATIONS FOUND ({len(all_violations)}):\n")
        for v in all_violations:
            print(v)
        print(f"\nFix all violations above before merging.")
        return 1

    print("✅ No staleness violations found.")
    return 0


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    sys.exit(main(root))
