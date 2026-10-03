# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Offline secret and variable updates; gh is always faked."""

import argparse
import getpass
import json
import warnings
from unittest.mock import Mock

import pytest

import set_shared_secret as shared
from gh_repos import RepoError

SECRET = "github_pat_example"


class FakeGh:
    """Stands in for gh; frozen repositories accept writes without storing them."""

    def __init__(self):
        self.calls = []
        self.secrets = {}
        self.variables = {}
        self.broken = set()
        self.frozen = set()
        self.clock = 0

    def __call__(self, *args, stdin=None):
        self.calls.append((args, stdin))
        command, repo = args[:2], args[args.index("--repo") + 1]
        if repo in self.broken:
            raise RepoError("HTTP 404: Not Found")
        if command == ("secret", "list"):
            stored = self.secrets.get(repo, {})
            return json.dumps([{"name": k, "updatedAt": v} for k, v in stored.items()])
        if command == ("secret", "set"):
            if repo not in self.frozen:
                self.clock += 1
                self.secrets.setdefault(repo, {})[args[2]] = f"t{self.clock}"
            return ""
        if command == ("variable", "set"):
            if repo not in self.frozen:
                self.variables[(repo, args[2])] = stdin
            return ""
        if command == ("variable", "get"):
            return json.dumps({"value": self.variables[(repo, args[2])]})
        raise AssertionError(f"unexpected gh call {args}")


@pytest.fixture
def fake_gh(monkeypatch):
    fake = FakeGh()
    monkeypatch.setattr(shared, "gh", fake)
    return fake


def test_names_are_stored_uppercase():
    assert shared.setting_name("repo_Mirror") == "REPO_MIRROR"
    assert shared.setting_name("_X1") == "_X1"


@pytest.mark.parametrize(
    "name", ["", "1X", "A-B", "A B", "GITHUB_TOKEN", "github_x", "É"]
)
def test_invalid_names(name):
    with pytest.raises(argparse.ArgumentTypeError):
        shared.setting_name(name)


def test_secret_goes_through_stdin_and_is_verified(fake_gh):
    fake_gh.secrets["o/r"] = {"REPO_MIRROR": "t0"}
    assert shared.set_secret("o/r", "REPO_MIRROR", SECRET) == "updated at t1"
    assert all(SECRET not in args for args, _ in fake_gh.calls)
    assert (("secret", "set", "REPO_MIRROR", "--repo", "o/r"), SECRET) in fake_gh.calls


def test_new_secret_is_verified(fake_gh):
    assert shared.set_secret("o/r", "NEW", SECRET) == "updated at t1"


@pytest.mark.parametrize(
    ("stored", "message"), [({}, "missing"), ({"OLD": "t0"}, "unchanged since t0")]
)
def test_unchanged_or_missing_secret_fails(fake_gh, stored, message):
    fake_gh.frozen.add("o/r")
    fake_gh.secrets["o/r"] = stored
    with pytest.raises(RepoError, match=message):
        shared.set_secret("o/r", "OLD", SECRET)


def test_variable_reads_back_value(fake_gh):
    assert shared.set_variable("o/r", "MIRROR_ENABLED", "true") == "reads back 'true'"
    assert fake_gh.variables == {("o/r", "MIRROR_ENABLED"): "true"}


def test_variable_mismatch_fails(fake_gh):
    fake_gh.frozen.add("o/r")
    fake_gh.variables[("o/r", "X")] = "old"
    with pytest.raises(RepoError, match="reads back 'old'"):
        shared.set_variable("o/r", "X", "new")


def prompt_for(typed):
    """Imitate getpass; None imitates a missing terminal."""

    def prompt(_):
        if typed is None:
            warnings.warn("Can not control echo", getpass.GetPassWarning)
        return typed

    return Mock(side_effect=prompt)


@pytest.fixture
def run_main(fake_gh, repos_file, monkeypatch, capsys):
    def run(*argv, typed=SECRET):
        prompt = prompt_for(typed)
        monkeypatch.setattr(shared.getpass, "getpass", prompt)
        path = repos_file("a\nb\nc\n")
        code = shared.main(["--repos", str(path), "--owner", "o", *argv])
        out, err = capsys.readouterr()
        return code, out, err, prompt

    return run


def test_secret_continues_past_failures(run_main, fake_gh):
    fake_gh.broken.add("o/b")
    code, out, err, prompt = run_main("--name", "repo_mirror")
    assert code == 1
    prompt.assert_called_once()
    assert set(fake_gh.secrets) == {"o/a", "o/c"}
    assert "FAILED  o/b" in err
    assert "REPO_MIRROR on 2 of 3" in out
    assert SECRET not in out + err


def test_variable_with_value(run_main, fake_gh):
    argv = ["--name", "MIRROR_ENABLED", "--variable", "--value", "true"]
    code, out, _, prompt = run_main(*argv)
    assert code == 0
    prompt.assert_not_called()
    assert len(fake_gh.variables) == 3
    assert "on 3 of 3" in out


def test_secret_rejects_command_line_value():
    with pytest.raises(SystemExit) as exit_info:
        shared.main(["--repos", "x", "--name", "X", "--value", SECRET])
    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    ("typed", "message"), [(None, "terminal is needed"), ("", "empty value")]
)
def test_unusable_secret_input_changes_nothing(run_main, fake_gh, typed, message):
    code, _, err, _ = run_main("--name", "X", typed=typed)
    assert code == 1
    assert fake_gh.calls == []
    assert message in err
