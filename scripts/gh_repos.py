# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Run the gh CLI against repositories listed in a file."""

import re
import subprocess
from pathlib import Path

# gh accepts [HOST/]OWNER/REPO; a bare REPO is qualified with the owner.
REPO = re.compile(r"[^\s/-][^\s/]*(?:/[^\s/]+){0,2}")


class RepoError(Exception):
    """A failed gh call or check must be reported, never assumed to work."""


def gh(*args, stdin=None):
    # Values travel on stdin so they never appear in the process list.
    try:
        result = subprocess.run(
            ["gh", *args], input=stdin, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise RepoError(f"Cannot run gh: {exc}") from exc
    if result.returncode:
        raise RepoError(result.stderr.strip() or f"gh exited {result.returncode}")
    return result.stdout


def read_repos(path, owner=None):
    names = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if REPO.fullmatch(line) is None:
            raise RepoError(f"Invalid repository: {line!r}")
        names.append(line)
    if not names:
        raise RepoError(f"{path} lists no repositories")
    if owner is None and any("/" not in name for name in names):
        owner = gh("api", "user", "--jq", ".login").strip()
    repos = [name if "/" in name else f"{owner}/{name}" for name in names]
    return list(dict.fromkeys(repos))
