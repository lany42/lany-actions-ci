# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Offline gh calls and repository lists; gh is always faked."""

import subprocess
from unittest.mock import Mock

import pytest

import gh_repos


def test_gh_passes_values_on_stdin_and_reports_failures(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "out", ""))
    monkeypatch.setattr(gh_repos.subprocess, "run", run)
    assert gh_repos.gh("secret", "set", "X", stdin="value") == "out"
    assert run.call_args.args == (["gh", "secret", "set", "X"],)
    assert run.call_args.kwargs["input"] == "value"
    run.return_value = subprocess.CompletedProcess([], 1, "", "HTTP 404")
    with pytest.raises(gh_repos.RepoError, match="HTTP 404"):
        gh_repos.gh("secret", "list")
    run.side_effect = FileNotFoundError("gh")
    with pytest.raises(gh_repos.RepoError, match="Cannot run gh"):
        gh_repos.gh("secret", "list")


def test_comments_blanks_duplicates_and_owner(monkeypatch, repos_file):
    gh = Mock(return_value="lany42\n")
    monkeypatch.setattr(gh_repos, "gh", gh)
    repos = gh_repos.read_repos(
        repos_file("# mirrors\n\n  a  \nother/b\na\nlany42/a\n")
    )
    gh.assert_called_once_with("api", "user", "--jq", ".login")
    assert repos == ["lany42/a", "other/b"]


def test_explicit_owner_skips_lookup(monkeypatch, repos_file):
    gh = Mock()
    monkeypatch.setattr(gh_repos, "gh", gh)
    repos = gh_repos.read_repos(repos_file("a\nghe.example/org/b\n"), "me")
    gh.assert_not_called()
    assert repos == ["me/a", "ghe.example/org/b"]


@pytest.mark.parametrize(
    "text", ["", "# none\n\n", "a b\n", "-R\n", "a//b\n", "a/b/c/d\n"]
)
def test_invalid_or_empty_lists(repos_file, text):
    with pytest.raises(gh_repos.RepoError):
        gh_repos.read_repos(repos_file(text), "me")
