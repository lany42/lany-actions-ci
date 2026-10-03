# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Offline publication decisions; Git and the registry are always faked."""

import io
import json
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import Mock, call

import pytest

import registry_publish as publish

COMMIT = "a" * 40
REPO = Path("checkout")


def test_numeric_release_and_rc_order():
    tags = [
        "v0.0.0",
        "v4.1.2-rc0",
        "v4.1.2-rc2",
        "v4.1.2-rc10",
        "v4.1.2-rc32",
        "v4.1.2",
        "v4.1.10",
        "v4.2.0",
        "v4.10.0",
        "v10.0.0",
    ]
    versions = [publish.parse_version(tag, tag=True) for tag in tags]
    assert versions == sorted(set(versions))


@pytest.mark.parametrize(
    "tag",
    [
        "v.0.2.0",
        "1.2.3",
        "v1.2",
        "v01.2.3",
        "v1.2.3-rc01",
        "v1.2.3-rc",
        "v1.2.3-beta1",
        "v1.2.3+build",
        "v1.2.3\n",
        "v1.2.3; echo unsafe",
        "",
        None,
    ],
)
def test_invalid_candidates(tag):
    with pytest.raises(publish.PublishError):
        publish.parse_version(tag, tag=True)


@pytest.mark.parametrize("version", ["4.1.2-rc32", "4.1.2rc32"])
def test_python_rc_spelling_matches_tag(version):
    candidate = publish.parse_version("v4.1.2-rc32", tag=True)
    assert publish.parse_version(version, python_rc=True) == candidate


@pytest.fixture
def git(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(publish, "git", fake)
    return fake


@pytest.fixture
def registry(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(publish, "latest_registry_version", fake)
    return fake


def test_automatic_selection_ignores_malformed_history(git, capsys):
    git.return_value = "v4.1.2-rc2\nv.0.2.0\nv4.1.2-rc32\nv4.1.1"
    assert publish.select_tag(REPO, "") == "v4.1.2-rc32"
    assert "v.0.2.0" in capsys.readouterr().out


def test_explicit_invalid_tag_fails_before_git(git):
    with pytest.raises(publish.PublishError):
        publish.select_tag(REPO, "v.0.2.0")
    git.assert_not_called()


def test_no_valid_tags_skips_without_registry_call(git, registry):
    git.return_value = "v.0.2.0\narchive"
    assert publish.decide(REPO)["publish"] == "false"
    registry.assert_not_called()


@pytest.mark.parametrize(
    ("latest", "expected"),
    [
        (None, "true"),
        ("4.1.1", "true"),
        ("4.1.2-rc32", "true"),
        ("4.1.2", "false"),
        ("4.2.0", "false"),
    ],
)
def test_newer_equal_older_and_first_publications(git, registry, latest, expected):
    git.side_effect = lambda repo, command, *args: (
        COMMIT
        if command == "rev-parse"
        else '[project]\nname = "registry-node"\nversion = "4.1.2"'
    )
    registry.return_value = latest
    decision = publish.decide(REPO, "v4.1.2")
    assert decision["publish"] == expected
    assert decision["commit"] == COMMIT
    registry.assert_called_once_with("registry-node")
    # Both annotated and lightweight tags must resolve to a commit, not a tag object.
    assert git.call_args_list == [
        call(REPO, "rev-parse", "--verify", "refs/tags/v4.1.2^{commit}"),
        call(REPO, "show", f"{COMMIT}:pyproject.toml"),
    ]


@pytest.mark.parametrize(
    "metadata",
    [
        "not toml",
        "[tool.other]\nx = 1",
        '[project]\nversion = "4.1.2"',
        '[project]\nname = "node"',
        '[project]\nname = "node"\nversion = "4.1.1"',
    ],
)
def test_bad_release_metadata_fails_before_registry(git, registry, metadata):
    git.side_effect = [COMMIT, metadata]
    with pytest.raises(publish.PublishError):
        publish.decide(REPO, "v4.1.2")
    registry.assert_not_called()


def test_nonexistent_tag_fails_without_registry(monkeypatch, registry):
    failure = subprocess.CompletedProcess([], 128, "", "unknown revision")
    monkeypatch.setattr(publish.subprocess, "run", Mock(return_value=failure))
    with pytest.raises(publish.PublishError, match="Git read failed"):
        publish.decide(REPO, "v4.1.2")
    registry.assert_not_called()


@pytest.fixture
def urlopen(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(publish.urllib.request, "urlopen", fake)
    return fake


def respond(urlopen, body, status=200):
    response = io.BytesIO(body)
    response.status = status
    urlopen.return_value = response


def test_all_statuses_and_numeric_order_are_considered(urlopen):
    versions = [
        {"version": "4.1.2", "status": "NodeVersionStatusActive"},
        {"version": "4.2.0", "status": "NodeVersionStatusDeleted"},
        {"version": "4.10.0-rc32", "status": "NodeVersionStatusFlagged"},
        {"version": "4.10.0-rc2", "status": "NodeVersionStatusPending"},
    ]
    respond(urlopen, json.dumps(versions).encode())
    assert publish.latest_registry_version("registry-node") == "4.10.0-rc32"
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.comfy.org/nodes/registry-node/versions"
    assert urlopen.call_args.kwargs["timeout"] == 30


def test_empty_list_is_the_only_empty_registry_result(urlopen):
    respond(urlopen, b"[]")
    assert publish.latest_registry_version("node") is None


@pytest.mark.parametrize(
    "data", [None, {}, {"versions": []}, [None], [{}], [{"version": "bad"}]]
)
def test_malformed_registry_versions_fail(urlopen, data):
    respond(urlopen, json.dumps(data).encode())
    with pytest.raises(publish.PublishError):
        publish.latest_registry_version("node")


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),
        urllib.error.URLError("DNS failed"),
        *[
            urllib.error.HTTPError("https://api.comfy.org", code, "failure", {}, None)
            for code in (401, 403, 404, 429, 500)
        ],
    ],
)
def test_http_and_connection_errors_fail(urlopen, error):
    urlopen.side_effect = error
    with pytest.raises(publish.PublishError, match="Registry request failed"):
        publish.latest_registry_version("node")


@pytest.mark.parametrize(
    ("body", "status"), [(b"[]", 204), (b"<html>unavailable</html>", 200)]
)
def test_unexpected_status_and_invalid_json_fail(urlopen, body, status):
    respond(urlopen, body, status)
    with pytest.raises(publish.PublishError):
        publish.latest_registry_version("node")


@pytest.fixture
def github_files(tmp_path, monkeypatch):
    output, summary = tmp_path / "output", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    return output, summary


def test_error_exits_nonzero_and_disables_publish(monkeypatch, github_files, capsys):
    output, summary = github_files
    error = publish.PublishError("Registry request failed: timed out")
    monkeypatch.setattr(publish, "decide", Mock(side_effect=error))
    assert publish.main([]) == 1
    assert output.read_text() == "publish=false\n"
    assert "::error::Registry request failed: timed out" in capsys.readouterr().err
    assert "Publication check failed" in summary.read_text()


def test_success_exports_exact_commit_and_decision(monkeypatch, github_files):
    output, summary = github_files
    decide = Mock(
        return_value={
            "publish": "true",
            "tag": "v4.1.2",
            "commit": COMMIT,
            "latest": "4.1.1",
            "reason": "Newer",
        }
    )
    monkeypatch.setattr(publish, "decide", decide)
    assert publish.main(["--repo", "checkout", "--tag", "v4.1.2"]) == 0
    decide.assert_called_once_with(REPO, "v4.1.2")
    assert output.read_text() == f"publish=true\ntag=v4.1.2\ncommit={COMMIT}\n"
    assert "4.1.1" in summary.read_text()
