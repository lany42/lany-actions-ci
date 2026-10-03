# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Offline mirror dispatches; gh is always faked."""

from unittest.mock import Mock, call

import pytest

import run_mirrors
from gh_repos import RepoError


@pytest.fixture
def gh(monkeypatch):
    def dispatch(*args):
        repo = args[args.index("--repo") + 1]
        if repo == "o/broken":
            raise RepoError("HTTP 404: Not Found")
        return f"https://github.com/{repo}/actions/runs/1\n"

    fake = Mock(side_effect=dispatch)
    monkeypatch.setattr(run_mirrors, "gh", fake)
    return fake


def run(repos_file, capsys, text):
    code = run_mirrors.main(["--repos", str(repos_file(text)), "--owner", "o"])
    out, err = capsys.readouterr()
    return code, out, err


def test_dispatches_mirror_on_main_in_every_repo(gh, repos_file, capsys):
    code, out, err = run(repos_file, capsys, "a\nother/b\n")
    assert code == 0
    assert gh.call_args_list == [
        call("workflow", "run", "mirror.yml", "--repo", repo, "--ref", "main")
        for repo in ("o/a", "other/b")
    ]
    assert "ok      o/a: https://github.com/o/a/actions/runs/1" in out
    assert "in 2 of 2" in out
    assert err == ""


def test_continues_past_failures(gh, repos_file, capsys):
    code, out, err = run(repos_file, capsys, "a\nbroken\nc\n")
    assert code == 1
    assert gh.call_count == 3
    assert "FAILED  o/broken: HTTP 404" in err
    assert "in 2 of 3" in out


def test_missing_run_url_still_reports_dispatch(gh, repos_file, capsys):
    gh.side_effect = None
    gh.return_value = ""
    code, out, _ = run(repos_file, capsys, "a\n")
    assert code == 0
    assert "ok      o/a: dispatched" in out


@pytest.mark.parametrize("text", ["", "a b\n"])
def test_invalid_list_dispatches_nothing(gh, repos_file, capsys, text):
    code, _, err = run(repos_file, capsys, text)
    assert code == 1
    gh.assert_not_called()
    assert err.startswith("error: ")
