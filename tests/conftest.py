# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Fixtures shared by the offline script tests."""

import subprocess

import pytest


@pytest.fixture(autouse=True)
def no_real_commands(monkeypatch):
    # A real gh call could change live repositories; tests fake every command.
    def forbid(*args, **kwargs):
        pytest.fail("Offline tests must not run real commands such as gh")

    monkeypatch.setattr(subprocess, "run", forbid)


@pytest.fixture
def repos_file(tmp_path):
    def write(text):
        path = tmp_path / "repos.txt"
        path.write_text(text)
        return path

    return write
