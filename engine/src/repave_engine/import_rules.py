"""Destination rules that map an existing repo's files onto a golden path layout.

Rules come from ``spec.import`` in ``blueprint.yaml`` when present, and otherwise from
per-family defaults here so every shipped blueprint can be imported before any of them
are annotated.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from posixpath import basename, join, normpath

UNMAPPED_KEEP = "keep-in-place"
UNMAPPED_QUARANTINE = "quarantine"
QUARANTINE_DIR = ".repave/unmapped"
OVERRIDE_KEEP = UNMAPPED_KEEP
OVERRIDE_QUARANTINE = UNMAPPED_QUARANTINE


@dataclass(frozen=True)
class ImportRule:
    """One match-to-destination mapping.

    ``preserve_tree`` keeps the source path untouched, which is how a subtree that is
    already correctly placed (``examples/``, ``templates/``) is declared.
    A ``destination`` of ``.`` or one ending in ``/`` is a directory and keeps the source
    basename; anything else is an exact destination path.
    """

    match: tuple[str, ...]
    destination: str = "."
    exclude: tuple[str, ...] = ()
    preserve_tree: bool = False


@dataclass(frozen=True)
class ImportRuleSet:
    rules: tuple[ImportRule, ...] = ()
    keep: tuple[str, ...] = ()
    unmapped: str = UNMAPPED_KEEP


_COMMON_KEEP: tuple[str, ...] = (
    "LICENSE",
    "LICENSE.*",
    "COPYING",
    "NOTICE",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".gitignore",
    ".gitattributes",
    ".git-blame-ignore-revs",
    ".github/CODEOWNERS",
    ".github/**",
)

_README_RULE = ImportRule(
    match=("README", "README.*", "readme", "readme.*"), destination="README.md"
)


_DEFAULT_IMPORT_RULES: dict[str, ImportRuleSet] = {
    "terraform": ImportRuleSet(
        rules=(
            _README_RULE,
            ImportRule(match=("examples/**", "example/**"), preserve_tree=True),
            ImportRule(match=("modules/**",), preserve_tree=True),
            ImportRule(match=("**/*.tftest.hcl",), destination="tests/"),
            ImportRule(match=("test/**", "tests/**"), destination="tests/"),
            ImportRule(
                match=("**/*.tf", "**/*.tfvars", "**/*.tf.json"),
                exclude=("examples/**", "example/**", "modules/**", "test/**", "tests/**"),
                destination=".",
            ),
            ImportRule(
                match=(".tflint.hcl", ".checkov.yml", ".terraform-docs.yml"), destination="."
            ),
        ),
        keep=_COMMON_KEEP,
    ),
    "ansible": ImportRuleSet(
        rules=(
            _README_RULE,
            ImportRule(
                match=(
                    "tasks/**",
                    "handlers/**",
                    "defaults/**",
                    "vars/**",
                    "meta/**",
                    "templates/**",
                    "files/**",
                    "molecule/**",
                    "library/**",
                    "filter_plugins/**",
                    "roles/**",
                    "plugins/**",
                    "playbooks/**",
                    "inventory/**",
                ),
                preserve_tree=True,
            ),
            ImportRule(
                match=("galaxy.yml", "requirements.yml", "ansible.cfg", ".ansible-lint"),
                destination=".",
            ),
            ImportRule(match=("*.yml", "*.yaml"), destination="."),
        ),
        keep=_COMMON_KEEP,
    ),
    "helm": ImportRuleSet(
        rules=(
            _README_RULE,
            ImportRule(match=("templates/**", "charts/**", "crds/**"), preserve_tree=True),
            ImportRule(
                match=(
                    "Chart.yaml",
                    "Chart.lock",
                    "values.yaml",
                    "values.schema.json",
                    ".helmignore",
                ),
                destination=".",
            ),
            ImportRule(match=("values-*.yaml", "values.*.yaml"), destination="."),
        ),
        keep=_COMMON_KEEP,
    ),
    "app": ImportRuleSet(
        rules=(
            _README_RULE,
            ImportRule(
                match=("src/**", "tests/**", "test/**", "cmd/**", "internal/**"), preserve_tree=True
            ),
            ImportRule(
                match=(
                    "Dockerfile",
                    "Dockerfile.*",
                    "pyproject.toml",
                    "package.json",
                    "go.mod",
                    "go.sum",
                    "Makefile",
                ),
                destination=".",
            ),
        ),
        keep=_COMMON_KEEP,
    ),
    "policy": ImportRuleSet(
        rules=(
            _README_RULE,
            ImportRule(match=("**/*.rego",), destination="policy/opa/policies/"),
            ImportRule(match=("**/fixtures/**",), destination="tests/fixtures/"),
            ImportRule(match=("**/*.py",), destination="policy/checkov/"),
            ImportRule(match=("**/*.json",), destination="policy/definitions/"),
        ),
        keep=_COMMON_KEEP,
    ),
    "observability": ImportRuleSet(
        rules=(
            _README_RULE,
            ImportRule(
                match=("dashboards/**", "monitors/**", "alerts/**", "rules/**"),
                preserve_tree=True,
            ),
            ImportRule(match=("**/*dashboard*.json",), destination="dashboards/"),
            ImportRule(match=("**/*monitor*.json",), destination="monitors/"),
            ImportRule(match=("**/*.rules.yml", "**/*.rules.yaml"), destination="rules/"),
        ),
        keep=_COMMON_KEEP,
    ),
}

_FALLBACK_RULES = ImportRuleSet(rules=(_README_RULE,), keep=_COMMON_KEEP)


def default_import_rules(family: str) -> ImportRuleSet:
    return _DEFAULT_IMPORT_RULES.get(family, _FALLBACK_RULES)


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def parse_import_rules(spec_import: object, *, family: str) -> ImportRuleSet:
    """Build a rule set from ``spec.import``, falling back to the family defaults."""
    if not isinstance(spec_import, Mapping):
        return default_import_rules(family)

    raw_rules = spec_import.get("rules")
    rules: list[ImportRule] = []
    if isinstance(raw_rules, Sequence) and not isinstance(raw_rules, str):
        for entry in raw_rules:
            if not isinstance(entry, Mapping):
                continue
            match = _as_str_tuple(entry.get("match"))
            if not match:
                continue
            rules.append(
                ImportRule(
                    match=match,
                    destination=str(entry.get("destination", ".")),
                    exclude=_as_str_tuple(entry.get("exclude")),
                    preserve_tree=bool(entry.get("preserveTree", False)),
                )
            )

    if not rules:
        rules = list(default_import_rules(family).rules)

    keep = _as_str_tuple(spec_import.get("keep")) or _COMMON_KEEP
    unmapped = str(spec_import.get("unmapped", UNMAPPED_KEEP))
    if unmapped not in (UNMAPPED_KEEP, UNMAPPED_QUARANTINE):
        unmapped = UNMAPPED_KEEP
    return ImportRuleSet(rules=tuple(rules), keep=keep, unmapped=unmapped)


def parse_path_overrides(raw: object) -> dict[str, str]:
    """Parse ``spec.import.overrides`` or a preview payload into source → action."""
    if not isinstance(raw, Mapping):
        return {}
    overrides: dict[str, str] = {}
    for source, action in raw.items():
        rel = str(source).strip().replace("\\", "/").lstrip("./")
        if not rel:
            continue
        if isinstance(action, Mapping):
            if action.get("keep") is True or action.get("keep-in-place") is True:
                overrides[rel] = OVERRIDE_KEEP
                continue
            if action.get("quarantine") is True:
                overrides[rel] = OVERRIDE_QUARANTINE
                continue
            destination = str(action.get("destination", "")).strip()
            if destination:
                overrides[rel] = destination
            continue
        text = str(action).strip()
        if text:
            overrides[rel] = text
    return overrides


def normalize_override_action(action: str) -> str:
    lowered = action.strip().lower()
    if lowered in ("keep", "keep-in-place", "leave", "unchanged"):
        return OVERRIDE_KEEP
    if lowered in ("quarantine", "unmapped"):
        return OVERRIDE_QUARANTINE
    return action.strip()


@lru_cache(maxsize=512)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a git-style glob into a regex anchored at the repo root."""
    out: list[str] = ["^"]
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(char))
            index += 1
    out.append("$")
    return re.compile("".join(out))


def matches_glob(rel_path: str, pattern: str) -> bool:
    if _glob_regex(pattern).match(rel_path) is not None:
        return True
    # A bare directory pattern ("tests/**") should also match the directory itself.
    if pattern.endswith("/**"):
        return _glob_regex(pattern[:-3]).match(rel_path) is not None
    return False


def matches_any(rel_path: str, patterns: Sequence[str]) -> bool:
    return any(matches_glob(rel_path, pattern) for pattern in patterns)


@dataclass(frozen=True)
class Classification:
    destination: str | None
    reason: str
    rule_index: int = -1
    kept: bool = field(default=False)


def classify_path(
    rel_path: str,
    rules: ImportRuleSet,
    *,
    path_overrides: Mapping[str, str] | None = None,
) -> Classification:
    """Return where ``rel_path`` belongs under the golden path layout.

    A destination of ``None`` means the file is unmapped and the caller applies the
    rule set's ``unmapped`` policy. Per-path overrides win over import rules.
    """
    if path_overrides and rel_path in path_overrides:
        action = normalize_override_action(path_overrides[rel_path])
        if action == OVERRIDE_KEEP:
            return Classification(
                destination=rel_path,
                reason="override: leave in place",
                kept=True,
            )
        if action == OVERRIDE_QUARANTINE:
            return Classification(
                destination=quarantine_path(rel_path),
                reason="override: quarantine",
            )
        destination = normpath(action)
        return Classification(
            destination=destination,
            reason=f"override: move to `{destination}`",
        )

    if matches_any(rel_path, rules.keep):
        return Classification(destination=rel_path, reason="kept in place by rule", kept=True)

    for index, rule in enumerate(rules.rules):
        if rule.exclude and matches_any(rel_path, rule.exclude):
            continue
        if not matches_any(rel_path, rule.match):
            continue
        pattern = next(p for p in rule.match if matches_glob(rel_path, p))
        if rule.preserve_tree:
            return Classification(
                destination=rel_path,
                reason=f"matched `{pattern}` (subtree preserved)",
                rule_index=index,
            )
        destination = _resolve_destination(rel_path, rule.destination)
        return Classification(
            destination=destination,
            reason=f"matched `{pattern}`",
            rule_index=index,
        )

    return Classification(destination=None, reason="no rule matched")


def _resolve_destination(rel_path: str, destination: str) -> str:
    target = destination.strip()
    if target in ("", ".", "./"):
        return basename(rel_path)
    if target.endswith("/"):
        return normpath(join(target, basename(rel_path)))
    return normpath(target)


def quarantine_path(rel_path: str) -> str:
    return normpath(join(QUARANTINE_DIR, rel_path))
