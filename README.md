# lany-actions-ci

Shared GitHub Actions for repositories hosted canonically on
`git.colorized.life`. GitHub serves only as a public mirror and free CI.

| Reference | Purpose |
| --- | --- |
| `lany42/lany-actions-ci/actions/mirror` | Anonymously fetch canonical branches and tags. Update the GitHub mirror with the `REPO_MIRROR` PAT, verify it, then optionally dispatch a workflow. |
| `lany42/lany-actions-ci/actions/registry-publish` | Publish the highest (or a selected) `vX.Y.Z[-rcN]` tag to the Comfy registry when it is newer than every registry version. |
| `lany42/lany-actions-ci/.github/workflows/rust-preflight.yml` | Reusable workflow that runs the checks to pass before `cargo publish` on the latest stable and nightly Rust, optionally for a target without std and under Miri. |

## Install

Reference the actions from `.github/workflows` in each repository. Pin them
to a full commit SHA from this repository's GitHub mirror:

```sh
git ls-remote https://github.com/lany42/lany-actions-ci.git refs/heads/main
```

The actions receive the mirror PAT and the registry key. A tag such as `v1`
could be moved by anyone who can push to the mirror, but a commit SHA cannot.

Repository settings are as before. Set the `MIRROR_ENABLED` and
`REGISTRY_PUBLISH_ENABLED` variables, along with the `REPO_MIRROR` and
`REGISTRY_ACCESS_TOKEN` Actions secrets.

### `.github/workflows/mirror.yml`

```yaml
name: Mirror canonical repository

# Enable MIRROR_ENABLED only after origin contains every intended commit and tag.
# REPO_MIRROR is a fine-grained PAT with Contents/Workflows write access to this mirror.
on:
  schedule:
    - cron: "43 */6 * * *" # use a different minute in each repository
  workflow_dispatch:

permissions: {}

concurrency:
  group: canonical-mirror
  cancel-in-progress: false

jobs:
  mirror:
    if: ${{ github.repository == 'lany42/REPOSITORY' && vars.MIRROR_ENABLED == 'true' }}
    permissions:
      actions: write # only for dispatch-workflow
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - name: Mirror canonical repository
        uses: lany42/lany-actions-ci/actions/mirror@COMMIT_SHA
        with:
          canonical-url: https://git.colorized.life/REPOSITORY.git
          token: ${{ secrets.REPO_MIRROR }}
          dispatch-workflow: publish.yml # omit without registry publishing
```

The repository guard keeps forks from running the job. Before pushing, the
action refuses to roll back `main`. It also refuses when canonical `main` no
longer contains the calling workflow file.

### `.github/workflows/publish.yml`

```yaml
name: Publish to Comfy registry

# The mirror dispatches this workflow on main after a verified synchronization.
# Leave REGISTRY_PUBLISH_ENABLED unset/false until ready to publish.
on:
  workflow_dispatch:
    inputs:
      tag:
        description: "Tag to publish; empty selects the highest vX.Y.Z[-rcN] tag"
        required: false
        default: ""
        type: string

permissions:
  contents: read

concurrency:
  group: registry-publish
  cancel-in-progress: false

jobs:
  publish-node:
    name: Publish Custom Node to registry
    if: >-
      github.ref == 'refs/heads/main' &&
      vars.REGISTRY_PUBLISH_ENABLED == 'true'
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - name: Publish Custom Node
        uses: lany42/lany-actions-ci/actions/registry-publish@COMMIT_SHA
        with:
          tag: ${{ inputs.tag }}
          token: ${{ secrets.REGISTRY_ACCESS_TOKEN }}
```

The action checks out every tag into `workflow/`. It then checks out the
selected release commit at the workspace root and publishes it with
`Comfy-Org/publish-node-action`. Version checks always come from the pinned
action, not from the repository being published.

When migrating from copied workflows, delete `.github/scripts/`.

## Rust preflight

In a Rust repository, set `dispatch-workflow: preflight.yml` in `mirror.yml`
and call the reusable workflow:

### `.github/workflows/preflight.yml`

```yaml
name: Rust preflight

# The mirror dispatches this workflow on main after a verified synchronization.
on:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: rust-preflight
  cancel-in-progress: true

jobs:
  preflight:
    uses: lany42/lany-actions-ci/.github/workflows/rust-preflight.yml@COMMIT_SHA
    with:
      freestanding-target: thumbv7em-none-eabi # omit for crates that need std
      miri-script: scripts/test-miri # omit without a Miri script
```

| Job | Checks |
| --- | --- |
| `stable`, `nightly` | `cargo test` and `cargo clippy --all-targets -- -D warnings`, with and without default features. `cargo fmt --all -- --check`, `cargo doc --no-deps --all-features` with warnings denied, and `cargo publish --dry-run`. |
| `stable TARGET`, `nightly TARGET` | `cargo check`, `cargo build --release` and `cargo clippy -- -D warnings` of the library for `freestanding-target`, with and without default features. |
| `nightly miri` | `cargo miri setup`, then `miri-script` with nightly active. |

Each job installs the latest toolchain with rustup, overriding any
`rust-toolchain.toml`. Nightly falls back to the newest one with every
component a job needs. Every cargo command passes `--locked`, so `Cargo.lock`
must be committed and current. A job runs all its checks even after one fails,
so a single run reports every failure. The default features must build without
std on the freestanding target. The dry run packages the crate and builds it
from the package without uploading; it only warns when the version is already
on crates.io. Publish by hand once every job is green.

## Update

Push changes to this repository's `origin` and let it mirror. Dispatch the
mirror to skip the wait:

```sh
gh workflow run mirror.yml --repo lany42/lany-actions-ci --ref main
```

Then replace `COMMIT_SHA` in each repository's workflows with the new commit.
A downstream workflow can reference only commits that already exist on
GitHub.

This repository mirrors itself with `.github/workflows/mirror.yml`, so it
needs a public GitHub repository and the same bootstrap as any other mirror.
That means adding it to the `REPO_MIRROR` PAT's repositories, adding the
secret and the `MIRROR_ENABLED` variable, and making one initial seed push.

## Shared secrets

Regenerating a PAT invalidates its old value, so every consumer needs the
new one. List the repositories one per line, as `OWNER/REPO` or as a bare
`REPO` owned by the `gh` account, then set the secret everywhere:

```sh
python3 scripts/set_shared_secret.py --repos mirrors.txt --name REPO_MIRROR
python3 scripts/set_shared_secret.py --repos mirrors.txt --name MIRROR_ENABLED \
  --variable --value true
```

The secret is read from a hidden prompt and passed to `gh` on standard input.
GitHub never returns secret values, so each secret is verified by checking
that its `updatedAt` changed. Variables are verified by reading their values
back. The script continues past failures, then exits non-zero if any
repository failed.

## Dispatch every mirror

Dispatch `mirror.yml` on `main` in every listed repository, for example after
rotating `REPO_MIRROR`:

```sh
python3 scripts/run_mirrors.py --repos mirrors.txt
```

It prints each run's URL and does not wait for results. A run that finds no
changes skips the authenticated push, so it does not test a new token.
