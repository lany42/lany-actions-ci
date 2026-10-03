# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Dispatch the mirror workflow in many repositories with the gh CLI."""

import argparse
import sys
from pathlib import Path

from gh_repos import RepoError, gh, read_repos

WORKFLOW = "mirror.yml"


def dispatch(repo):
    # Without a terminal, gh prints only the URL of the run it created.
    url = gh("workflow", "run", WORKFLOW, "--repo", repo, "--ref", "main").strip()
    return url or "dispatched"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos",
        type=Path,
        required=True,
        help="file with one [HOST/]OWNER/REPO or REPO per line; # starts a comment",
    )
    parser.add_argument(
        "--owner", help="owner of bare REPO lines (default: the gh account)"
    )
    args = parser.parse_args(argv)
    try:
        repos = read_repos(args.repos, args.owner)
    except (RepoError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    failed = []
    for repo in repos:
        try:
            print(f"ok      {repo}: {dispatch(repo)}")
        except RepoError as exc:
            failed.append(repo)
            print(f"FAILED  {repo}: {exc}", file=sys.stderr)
    print(f"Dispatched {WORKFLOW} in {len(repos) - len(failed)} of {len(repos)}.")
    # Runs finish asynchronously; dispatching does not wait for their results.
    print("Check each run in GitHub Actions for the mirror result.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
