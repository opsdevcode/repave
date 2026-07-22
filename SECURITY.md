# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report privately via GitHub Security Advisories ("Report a
vulnerability" on the repository's Security tab), or contact the maintainer
directly. Include:

- A description of the issue and its impact.
- Steps to reproduce (proof-of-concept if possible).
- Affected version/commit.

You can expect an initial acknowledgment within a few business days.

## Scope and design notes

`repave` is designed so that generated artifacts cannot bypass their configured
quality/security gates. Security-relevant expectations:

- The engine writes generated modules only to the configured `modules_root`
  outside the repave repository; it never commits module output into the repave
  repo itself.
- Credentials (e.g. GitHub tokens, cloud credentials) are provided at runtime and
  must never be committed, logged, or embedded in generated output.
- Prefer short-lived, least-privilege credentials (OIDC/workload identity) for
  any automated PR or apply path.

Reports that demonstrate a way to bypass gates, exfiltrate credentials, or cause
the engine to generate unsafe artifacts are especially valuable.
