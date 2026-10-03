"""The datacontract command, including check-pr against a real temporary git repository."""

import shutil
import subprocess
from pathlib import Path

import pytest

from data_contracts_platform.cli import main

ROOT = Path(__file__).resolve().parents[2]
ORDERS = ROOT / "contracts" / "orders.yaml"


def git(repo: Path, *args: str) -> None:
    """Run git quietly inside repo."""
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)  # noqa: S603, S607


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repo whose main branch publishes contracts/orders.yaml."""
    (tmp_path / "contracts").mkdir()
    shutil.copy(ORDERS, tmp_path / "contracts" / "orders.yaml")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "-c", "user.name=test", "-c", "user.email=test@example.com", "add", ".")
    git(
        tmp_path,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-q",
        "-m",
        "publish",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return tmp_path


def edit(path: Path, old: str, new: str) -> None:
    """Replace text once in a file."""
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_validate_ok_and_invalid(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("apiVersion: v3.0.2\nkind: Table\n", encoding="utf-8")
    assert main(["validate", str(ORDERS)]) == 0
    assert main(["validate", str(ORDERS), str(bad)]) == 2
    assert "invalid" in capsys.readouterr().out


def test_diff_exit_codes(tmp_path, capsys):
    new = tmp_path / "orders.yaml"
    shutil.copy(ORDERS, new)
    assert main(["diff", str(ORDERS), str(new)]) == 0
    edit(new, "unit: h", "unit: d")
    assert main(["diff", str(ORDERS), str(new)]) == 1
    assert "BREAKING" in capsys.readouterr().out
    assert main(["diff", str(ORDERS), str(tmp_path / "missing.yaml")]) == 2


def test_check_pr_passes_safe_change(repo):
    edit(repo / "contracts" / "orders.yaml", "unit: h", "unit: min")  # 1 h -> 1 min, tighter
    assert main(["check-pr", "--base", "main"]) == 0


def test_check_pr_blocks_breaking_change_and_writes_summary(repo, monkeypatch):
    summary = repo / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    edit(
        repo / "contracts" / "orders.yaml",
        "[placed, paid, shipped, cancelled]",
        "[placed, paid, shipped, cancelled, refunded]",
    )
    assert main(["check-pr", "--base", "main"]) == 1
    text = summary.read_text(encoding="utf-8")
    assert "**breaking** `orders.status` allowed-values-extended" in text
    assert "must not merge" in text


def test_check_pr_new_and_removed_contracts(repo):
    shutil.copy(ORDERS, repo / "contracts" / "orders_v2.yaml")
    assert main(["check-pr", "--base", "main"]) == 0  # a new contract is safe
    (repo / "contracts" / "orders.yaml").unlink()
    assert main(["check-pr", "--base", "main"]) == 1  # removing a published one is breaking


@pytest.mark.parametrize("ref", ["--output=/tmp/x", "-p", "main..HEAD", "main;rm", "a b"])
def test_check_pr_rejects_option_like_refs(repo, ref, capsys):
    assert main(["check-pr", f"--base={ref}"]) == 2  # = form, so argparse passes it through
    assert "refusing unusual git ref" in capsys.readouterr().err
