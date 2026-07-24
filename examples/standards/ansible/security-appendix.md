# Ansible security appendix

Version: 1.0.0

Cross-cutting security rules for all repave Ansible artifact types. Mapped to
enforceable gates where possible.

## Secrets and credentials

| Rule | Enforcement |
| --- | --- |
| No passwords, tokens, or private keys in repo | `secrets` gate (Checkov secrets framework) |
| Sensitive task output not logged | ansible-lint `no-log-password` (opt-in) |
| Vault for required secrets | Document in README; gate cannot verify vault usage |

## Module and task safety

| Rule | Enforcement |
| --- | --- |
| Avoid non-deterministic package state (`latest`) | ansible-lint `safety` profile rules |
| No implicit privilege / ownership changes | `no-same-owner` (opt-in) |
| Safe file permissions on copy/template | `risky-file-permissions`, `risky-octal` |
| No unsafe shell pipes | `risky-shell-pipe` |

## Supply chain

- Pin collection and role versions in `requirements.yml` or `galaxy.yml`.
- Review third-party role dependencies before `meta/main.yml` dependencies.
- Document upgrade cadence in README.

## Logging and audit

- Use `no_log: true` on authentication and key material tasks.
- Avoid registering sensitive command output.

## Hardening-oriented roles

For CIS/STIG-style hardening roles, follow variable-driven design (see
ansible-lockdown patterns): toggles in `defaults/main.yml`, tagged tasks, test in
non-production first. Do not vendor benchmark text into repave; link external
benchmark versions in role documentation.

## Exceptions

Exceptions require README rationale and `.ansible-lint-ignore` entries. Security
exceptions need platform team approval.
