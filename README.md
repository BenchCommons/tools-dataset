# tools-dataset

Builds, validates and exports BenchCommons datasets and delivers pinned inputs to the catalogs and tools-benchmark.

This repo owns the **input contract** for every `dataset-*` repo (see [CONTRACTS.md](https://github.com/BenchCommons/.product/blob/main/CONTRACTS.md), spec [001](docs/specs/001-input-contract/spec.md)) and the **source toolkit** they share (spec [004](docs/specs/004-source-toolkit/spec.md)): a download cache, a spreadsheet reader, the adapter base and the source registry.

## Use from a dataset repo

```toml
[project]
dependencies = ["benchcommons-tools-dataset==0.1.0"]

[tool.uv.sources]
benchcommons-tools-dataset = { git = "https://github.com/BenchCommons/tools-dataset", tag = "v0.1.0" }
```

```python
from datasettool.sources.cache import fetch_resource
from datasettool.sources.spreadsheet import rows
```

To pin a commit instead of a tag, use `rev = "<full 40-character SHA>"` in place of `tag`. Commit the `uv.lock`: it records the toolkit with a `git` source and the commit SHA.

### What is supported

Prerequisites: `uv`, Python 3.12 or later, and network access to `github.com` when resolving or syncing without a cache.

- Supported: `uv lock`, `uv sync --locked` and `uv add` in a project whose `[tool.uv.sources]` pins this repo to a tag or a commit, as above. Check it with `grep -A2 '^name = "benchcommons-tools-dataset"' uv.lock`: the `source` line of that package entry must be `git = "https://github.com/BenchCommons/tools-dataset?tag=vX.Y.Z#<sha>"` (or `?rev=`), never `registry`.
- Supported, one-off: `pip install "benchcommons-tools-dataset @ git+https://github.com/BenchCommons/tools-dataset@vX.Y.Z"`.
- Not supported: installers that ignore `[tool.uv.sources]` (`pip install .` in a dataset repo, `pip install` of a built dataset wheel, Poetry, pip-tools). They look the name up on PyPI, where it is not registered ([#10](https://github.com/BenchCommons/tools-dataset/issues/10)).
- Cloning this repo and running `uv sync --locked` in it is for developing the toolkit. It is not how a dataset repo consumes it.

See [ADR 0004](docs/adr/0004-dataset-repos-depend-on-a-git-tag.md) and [ADR 0008](docs/adr/0008-supported-installs-are-uv-with-a-pinned-git-source.md). Specs live in `docs/specs/<NNN>-<feature>/`.

## License

Code: Apache-2.0 ([`LICENSE`](LICENSE)).
