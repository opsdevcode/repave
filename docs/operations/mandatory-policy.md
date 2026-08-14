# Mandatory policy on regulated families

v3 opt-in that refuses `enable_policy: false` (and the OPA "policy pack not
enabled" skip) on configured blueprint families. Waivers with enforced expiry
are the only skip path. Decision function: `decide_policy_skip()` in
`engine/src/repave_engine/mandatory_policy.py`.

Do not default-on `v3.enabled` or `v3.mandatory_policy.enabled` in hosted values.

## When to use this

| Situation | Action |
| --- | --- |
| Estate must not generate terraform/policy/gitops without OPA | Enable the [opt-in](#1-opt-in) |
| One entity cannot run OPA yet | Add a [waiver](#2-waiver) with `expires_at` |
| Family should stay optional (for example observability in a lab) | Remove it from `regulated_families` |

## 1. Opt-in

```yaml
v3:
  enabled: true
  mandatory_policy:
    enabled: true
    # omitted list uses the engine default (terraform, policy, gitops, helm,
    # ansible, observability)
    regulated_families:
      - terraform
      - policy
      - gitops
      - helm
      - ansible
      - observability
```

Helm:

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  --set repave.v3.enabled=true \
  --set repave.v3.mandatoryPolicy.enabled=true
```

`v3.mandatory_policy.enabled` requires `v3.enabled`. Generate and plan then
reject `enable_policy: false` on those families. The message names
`enable_policy: true`, the waivers file, or `regulated_families`.

## 2. Waiver

JSONL at `v3.waivers_file` (default `data/waivers.jsonl`). `gate_id` must be
`mandatory-policy`. Expired rows do not skip.

```json
{"waiver_id":"obs-opa-q3","gate_id":"mandatory-policy","expires_at":"2026-12-01T00:00:00Z","entity_id":"monitors-platform-checkout","reason":"pack not ready"}
```

Omit `entity_id` to cover every entity. Renew or delete the row before
`expires_at`; an expired waiver fails closed and names the file.

## 3. Local demonstration

```bash
# from a scratch checkout with v3.mandatory_policy.enabled: true
cd engine
uv run pytest tests/test_mandatory_policy.py -q --no-cov
```

Expect `enable_policy: false` on `monitors-as-code-generic` to raise a
`ValueError` that names `enable_policy: true` and `gate_id: mandatory-policy`.

## Related

- [`repave.config.yaml.example`](../../repave.config.yaml.example) — `v3.mandatory_policy` knobs
- [`docs/v3-development.md`](../v3-development.md) — foundation slice
- [`docs/operations/auto-merge-revert.md`](auto-merge-revert.md) — waiver expiry on auto-merge
