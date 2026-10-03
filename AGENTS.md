If a push is requested, only push to `origin`. Never push to a mirror remote unless the user explicitly overrides this rule.

# Development workflow

Other repositories pin these actions by commit SHA from the GitHub mirror.
Pass action inputs to scripts through `env`, never by expanding `${{ }}`
inside `run`.

Scripts in `actions/` and `scripts/` run standalone with `python3`. Keep
them on the standard library and compatible with Python 3.12, the system
interpreter on ubuntu-24.04 runners. The uv workspace holds only
development tools, and tests live in `tests/`.

Run from the repository root. Use the Python version in `.python-version`
and uv; `uv sync --locked` installs the development environment. Update
`pyproject.toml` and `uv.lock` together. Install the `actionlint` binary
from its GitHub releases rather than a Python wrapper. After changes, run
these checks in order:

```sh
uv run --offline --locked ruff check --fix .
uv run --offline --locked ruff format .
uv run --offline --locked ruff check .
uv run --offline --locked pytest
actionlint
uv lock --check
```

Every Python source and test starts with:

```python
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>
```

Use Conventional Commits: `<type>[optional scope][!]: <summary>`. Write an
imperative subject of at most 50 characters, with no trailing period. Follow
it with one blank line and a single short paragraph explaining what changed
and why in plain language. Limit the body to four lines, each at most 72
characters; avoid lists and exhaustive change logs.
