If a push is requested, only push to `origin`. Never push to a mirror remote unless the user explicitly overrides this rule.

# Development workflow

Other repositories pin these actions by commit SHA from the GitHub mirror.
Pass action inputs to scripts through `env`, never by expanding `${{ }}`
inside `run`. Run from the repository root:

```sh
uvx ruff check --fix .
uvx ruff format .
python3 -m unittest discover -s actions/registry-publish
uvx --from actionlint-py actionlint
```

Every Python source starts with:

```python
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Lany Atwood <lany@colorized.life>
```

Use Conventional Commits: `<type>[optional scope][!]: <summary>`. Write an
imperative subject of at most 50 characters, with no trailing period. Follow
it with one blank line and a single short paragraph explaining what changed
and why in plain language. Limit the body to four lines, each at most 72
characters; avoid lists and exhaustive change logs.
