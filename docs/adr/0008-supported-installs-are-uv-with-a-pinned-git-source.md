# 0008. Supported installs: uv with a pinned git source; the PyPI name stays unregistered

## Status

Proposed. Spec [004](../specs/004-source-toolkit/spec.md). Amends [ADR 0004](0004-dataset-repos-depend-on-a-git-tag.md). Issue [#10](https://github.com/BenchCommons/tools-dataset/issues/10).

## Context

Dataset repos declare `benchcommons-tools-dataset==X.Y.Z` in `[project] dependencies` and resolve it through `[tool.uv.sources]` (ADR 0004). An installer that ignores `[tool.uv.sources]` (`pip install .`, `pip install` of a built dataset wheel, Poetry, pip-tools) looks the name up on PyPI, where it is not registered. Whoever registers it first would have their code installed in place of the toolkit (dependency confusion).

| Option | Cost | Effect on the risk |
|---|---|---|
| Reserve the name on PyPI under the organisation | A PyPI account and project, ownership to maintain; departs from "no PyPI publication" in ADR 0004 | Removes it for every installer |
| Document that installs are uv-only, with an explicit pinned URL for pip | Documentation only | Leaves the name unregistered; unsupported installers stay exposed |

## Decision

- Supported: `uv` (`uv sync --locked`, `uv lock`, `uv add`) with `[tool.uv.sources]` pointing at this repo's git URL, pinned to a release tag (`tag = "vX.Y.Z"`) or to a full commit SHA (`rev = "<40 hex>"`), and the resulting `uv.lock` committed. `uv.lock` then records the toolkit with a `git` source and the commit SHA, not a registry.
- Also supported for a one-off install: a direct reference with the same pin, `pip install "benchcommons-tools-dataset @ git+https://github.com/BenchCommons/tools-dataset@vX.Y.Z"`. A direct reference does not look the name up on an index.
- Not supported: any install that resolves `benchcommons-tools-dataset` by name from an index, such as `pip install .` in a dataset repo, installing a dataset wheel with `pip`, Poetry or pip-tools. Dataset repos state this in their docs.
- The name is not registered on PyPI now. This ADR does not prohibit registering it later. If the owner chooses to, a placeholder or a real release goes in a new ADR that supersedes this one.
- A checkout of this repo (`uv sync --locked` inside it, for development and tests) is not a consumer install. A consumer never installs from a checkout path.

## Consequences

- The risk is mitigated by documentation, not removed: someone who installs a dataset repo with an unsupported tool can still fetch a squatted package. Only reserving the name removes it.
- No code, dependency or release changes.
