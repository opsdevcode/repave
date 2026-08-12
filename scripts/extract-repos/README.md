# git filter-repo extraction scripts for v3 multi-repo split.
# See docs/adr/007-v3-multi-repo-decomposition.md and repos/README.md.

| Script | Target repo |
| --- | --- |
| `extract-corpus.sh` | `opsdevcode/repave-corpus` |
| `extract-operator.sh` | `opsdevcode/repave-operator` |
| `extract-cli.sh` | `opsdevcode/repave-cli` |

Requires `git-filter-repo` (`pip install git-filter-repo`). Each script clones the umbrella
repo and rewrites history to include only the paths for that artifact.

Python engine split (`repave-core`, `repave-server`, `repave-worker`) uses package manifests
under `packages/` and will get extraction scripts when Phase 3 module moves land.
