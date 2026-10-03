"""Command line: validate contracts, diff two versions, or check a pull request against its base.

Exit codes: 0 = valid / only safe changes, 1 = breaking change, 2 = invalid input or error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from data_contracts_platform import gitbase
from data_contracts_platform.contract import ContractError, load, loads
from data_contracts_platform.diff import Change, diff, is_breaking


def main(argv: list[str] | None = None) -> int:
    """Entry point for the datacontract command."""
    parser = argparse.ArgumentParser(prog="datacontract", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="validate contract files")
    v.add_argument("files", nargs="+", type=Path)
    d = sub.add_parser("diff", help="classify changes between two contract files")
    d.add_argument("old", type=Path)
    d.add_argument("new", type=Path)
    c = sub.add_parser("check-pr", help="diff every contract against the version at a git ref")
    c.add_argument("--base", required=True, help="published version, e.g. origin/main")
    c.add_argument("folder", type=Path, nargs="?", default=Path("contracts"))
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args.files)
        if args.command == "diff":
            changes = diff(load(args.old), load(args.new))
            _report(str(args.new), changes)
            return 1 if is_breaking(changes) else 0
        return _check_pr(args.base, args.folder)
    except (ContractError, gitbase.GitError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


def _validate(files: list[Path]) -> int:
    """Validate each file and report problems."""
    status = 0
    for f in files:
        try:
            c = load(f)
            print(f"ok       {f} ({c.id} {c.version}, {len(c.datasets)} dataset(s))")
        except ContractError as err:
            print(f"invalid  {err}")
            status = 2
    return status


def _check_pr(base: str, folder: Path) -> int:
    """Compare the working tree's contracts with the ones published at base."""
    repo = Path()
    current = {p.as_posix() for p in folder.rglob("*") if p.suffix in (".yaml", ".yml")}
    published = set(gitbase.files_at(base, folder, repo))
    breaking = False
    lines = [f"## Data contract check against `{base}`", ""]
    for path in sorted(current | published):
        if path not in current:
            changes = [
                Change("contract-removed", path, True, "every consumer of this contract breaks")
            ]
        elif path not in published:
            c = load(path)
            changes = [Change("contract-added", c.id, False, f"new contract {c.id} {c.version}")]
        else:
            old = loads(gitbase.show(base, Path(path), repo) or "", source=f"{base}:{path}")
            changes = diff(old, load(path))
        breaking |= is_breaking(changes)
        _report(path, changes)
        lines += [f"### `{path}`", ""] + [
            f"- {'**breaking**' if c.breaking else 'safe'} `{c.path}` {c.kind}: {c.detail}"
            for c in changes
        ]
        lines.append("" if changes else "- no changes\n")
    verdict = (
        "Breaking changes found: this pull request must not merge as is."
        if breaking
        else "No breaking changes."
    )
    lines.append(f"\n**{verdict}**")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print(verdict)
    return 1 if breaking else 0


def _report(name: str, changes: list[Change]) -> None:
    """Print one file's changes."""
    print(f"{name}: {len(changes)} change(s), {sum(c.breaking for c in changes)} breaking")
    for c in changes:
        print(f"  {c}")


if __name__ == "__main__":
    sys.exit(main())
