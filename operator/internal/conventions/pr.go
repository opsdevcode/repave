package conventions

import (
	"fmt"
	"os"
	"strings"
)

const (
	envBranchPrefixUpgrade = "REPAVE_PR_BRANCH_PREFIX_UPGRADE"
	envLabels              = "REPAVE_PR_LABELS"
	envEvidenceChecklist   = "REPAVE_PR_EVIDENCE_CHECKLIST"
)

// PullRequestDefaults mirror engine pull_requests conventions for operator remediation.
type PullRequestDefaults struct {
	BranchPrefixUpgrade string
	Labels              []string
	EvidenceChecklist   bool
}

// LoadPullRequestDefaults reads governed PR defaults from the environment.
func LoadPullRequestDefaults() PullRequestDefaults {
	prefix := strings.TrimSpace(os.Getenv(envBranchPrefixUpgrade))
	if prefix == "" {
		prefix = "repave/upgrade"
	}
	labels := parseCSV(os.Getenv(envLabels))
	if len(labels) == 0 {
		labels = []string{"repave", "governed"}
	}
	evidence := true
	if raw := strings.TrimSpace(os.Getenv(envEvidenceChecklist)); raw != "" {
		evidence = strings.EqualFold(raw, "true") || raw == "1"
	}
	return PullRequestDefaults{
		BranchPrefixUpgrade: prefix,
		Labels:              labels,
		EvidenceChecklist:   evidence,
	}
}

// UpgradeTitle returns the governed remediation PR title.
func UpgradeTitle(blueprintName, desiredVersion string) string {
	return fmt.Sprintf("chore(repave): upgrade %s to %s", blueprintName, desiredVersion)
}

// UpgradeBody renders the remediation PR body with optional upgrade diff summary.
func UpgradeBody(summary, blueprintName, desiredVersion, standardVersion string, evidence string) string {
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
	if strings.TrimSpace(evidence) != "" {
		lines = append(lines, "", evidence)
	}
	if strings.TrimSpace(summary) != "" {
		lines = append(lines, "", "### Upgrade diff", summary)
	}
	lines = append(lines, "", "## Evidence checklist", "- [ ] Upgrade plan reviewed", "- [ ] Gates green on remediation branch")
	return strings.Join(lines, "\n") + "\n"
}

func parseCSV(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}
