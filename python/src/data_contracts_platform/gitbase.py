"""Read files as they were at a git ref (the published version of a contract)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Branch, tag, remote-tracking or commit names only; never something git could read as an option.
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class GitError(RuntimeError):
    """git failed or the ref is not acceptable."""


def show(ref: str, path: Path, repo: Path = Path()) -> str | None:
    """File contents at ref, or None if the file did not exist there."""
    _check_ref(ref)
    rel = path.resolve().relative_to(repo.resolve()).as_posix()
    result = subprocess.run(  # noqa: S603 (fixed argv, no shell)
        ["git", "show", f"{ref}:{rel}"],  # noqa: S607 (git from PATH, like any developer tool)
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    if "does not exist" in result.stderr or "exists on disk, but not in" in result.stderr:
        return None
    raise GitError(result.stderr.strip() or f"git show failed for {ref}:{rel}")


def files_at(ref: str, folder: Path, repo: Path = Path()) -> list[str]:
    """Contract paths (relative to repo) under folder at ref."""
    _check_ref(ref)
    rel = folder.resolve().relative_to(repo.resolve()).as_posix()
    result = subprocess.run(  # noqa: S603 (fixed argv, no shell)
        ["git", "ls-tree", "-r", "--name-only", ref, "--", rel],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line.endswith((".yaml", ".yml"))]


def _check_ref(ref: str) -> None:
    """Reject refs that are not plain names."""
    if not REF.match(ref) or ".." in ref:
        raise GitError(f"refusing unusual git ref {ref!r}")
