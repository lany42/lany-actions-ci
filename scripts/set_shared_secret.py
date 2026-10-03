# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>

"""Set one Actions secret, or variable, on many repositories with the gh CLI."""

import argparse
import getpass
import json
import re
import sys
import warnings
from pathlib import Path

from gh_repos import RepoError, gh, read_repos

# GitHub's naming rules for secrets and variables; it stores names as uppercase.
NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


def setting_name(value):
    name = value.upper()
    if NAME.fullmatch(name) is None or name.startswith("GITHUB_"):
        raise argparse.ArgumentTypeError(
            f"{value!r} must use only letters, digits and underscores, "
            "and not start with a digit or GITHUB_"
        )
    return name


def secret_updated_at(repo, name):
    secrets = json.loads(
        gh("secret", "list", "--repo", repo, "--json", "name,updatedAt")
    )
    return next((s["updatedAt"] for s in secrets if s["name"] == name), None)


def set_secret(repo, name, value):
    # Secret values cannot be read back, so confirm GitHub recorded a new write.
    before = secret_updated_at(repo, name)
    gh("secret", "set", name, "--repo", repo, stdin=value)
    after = secret_updated_at(repo, name)
    if after is None:
        raise RepoError("secret is missing after it was set")
    if after == before:
        raise RepoError(f"secret is unchanged since {before}")
    return f"updated at {after}"


def set_variable(repo, name, value):
    gh("variable", "set", name, "--repo", repo, stdin=value)
    actual = json.loads(gh("variable", "get", name, "--repo", repo, "--json", "value"))
    if actual.get("value") != value:
        raise RepoError(f"variable reads back {actual.get('value')!r}")
    return f"reads back {value!r}"


def read_value(args):
    if not args.variable:
        # Without a terminal, getpass would warn and then read with echo.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                value = getpass.getpass(f"{args.name} (input hidden): ")
            except getpass.GetPassWarning as exc:
                raise RepoError("A terminal is needed to hide the secret") from exc
    elif args.value is None:
        value = input(f"{args.name}: ")
    else:
        value = args.value
    if not value:
        raise RepoError("Refusing to set an empty value")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos",
        type=Path,
        required=True,
        help="file with one [HOST/]OWNER/REPO or REPO per line; # starts a comment",
    )
    parser.add_argument(
        "--name", type=setting_name, required=True, help="such as REPO_MIRROR"
    )
    parser.add_argument(
        "--owner", help="owner of bare REPO lines (default: the gh account)"
    )
    parser.add_argument(
        "--variable", action="store_true", help="set a plain Actions variable instead"
    )
    parser.add_argument(
        "--value", help="variable value; without it, the value is prompted for"
    )
    args = parser.parse_args(argv)
    if args.value is not None and not args.variable:
        parser.error("secrets are read only from the hidden prompt, not --value")
    kind = "variable" if args.variable else "secret"
    try:
        repos = read_repos(args.repos, args.owner)
        print(f"Setting {kind} {args.name} on:", *repos, sep="\n  ", flush=True)
        value = read_value(args)
    except (RepoError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled before any repository was changed.", file=sys.stderr)
        return 130
    update = set_variable if args.variable else set_secret
    failed = []
    for repo in repos:
        try:
            print(f"ok      {repo}: {update(repo, args.name, value)}")
        except RepoError as exc:
            failed.append(repo)
            print(f"FAILED  {repo}: {exc}", file=sys.stderr)
    print(f"Set {kind} {args.name} on {len(repos) - len(failed)} of {len(repos)}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
