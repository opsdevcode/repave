package remediation

import (
	"fmt"
	"strings"
)

const (
	PRStateOpen    = "Open"
	PRStatePlanned = "Planned"
)

// UpgradeBranchName builds a deterministic branch name for a desired blueprint pin.
func UpgradeBranchName(prefix, blueprintName, blueprintVersion string) string {
	prefix = strings.TrimSpace(prefix)
	if prefix == "" {
		prefix = "repave/upgrade"
	}
	safeName := sanitizeBranchSegment(blueprintName)
	safeVersion := sanitizeBranchSegment(blueprintVersion)
	return fmt.Sprintf("%s/%s-%s", strings.TrimSuffix(prefix, "/"), safeName, safeVersion)
}

func sanitizeBranchSegment(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "unknown"
	}
	var b strings.Builder
	for _, r := range value {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9':
			b.WriteRune(r)
		case r == '.', r == '-', r == '_':
			b.WriteRune(r)
		default:
			b.WriteRune('-')
		}
	}
	return b.String()
}

// PullRequestTitle returns a governed title for remediation PRs.
func PullRequestTitle(blueprintName, desiredVersion string) string {
	return fmt.Sprintf("chore(repave): upgrade %s to %s", blueprintName, desiredVersion)
}

// PullRequestBody summarizes the upgrade for reviewers.
func PullRequestBody(summary, blueprintName, desiredVersion, standardVersion string) string {
	lines := []string{
		"## Summary",
		fmt.Sprintf(
			"Automated remediation from the repave operator for blueprint `%s` v%s.",
			blueprintName,
			desiredVersion,
		),
		"",
		fmt.Sprintf("- Standard version: `%s`", standardVersion),
		"- Never merge without review; rollback by closing this PR.",
	}
	if strings.TrimSpace(summary) != "" {
		lines = append(lines, "", "### Upgrade diff", summary)
	}
	return strings.Join(lines, "\n") + "\n"
}

// BaseBranch returns the configured base branch or main.
func BaseBranch(configured string) string {
	configured = strings.TrimSpace(configured)
	if configured == "" {
		return "main"
	}
	return configured
}
