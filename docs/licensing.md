# Licensing

This GitHub repository stays **public** so GitHub Actions continues to run on
the public-repo plan. Visibility is not an OSI open-source grant.

| Path | License |
| --- | --- |
| `docs/concepts.md`, `docs/adr/**` | Apache-2.0 — [LICENSE-CONCEPTS](../LICENSE-CONCEPTS) |
| Everything else | Proprietary source-available — [LICENSE](../LICENSE) |

Historical GitHub Releases and forks created while the tree was Apache-2.0
remain under that license. This file describes the default branch going
forward.

Third-party dependencies keep their own licenses (for example Copier, Kubernetes
libraries, Grafana dashboard MIT). Ansible fixture `license:` fields under
`examples/ansible-lint/tests/fixtures/` are Galaxy metadata examples, not this
product's license.

## relay

Apply the same split in [opsdevcode/relay](https://github.com/opsdevcode/relay)
as a separate pull request: proprietary `LICENSE`, Apache-2.0 `LICENSE-CONCEPTS`
for that repo's concepts and ADRs (if present), and matching README / package
metadata. Keep that repository public if it should stay on the public Actions
plan.
