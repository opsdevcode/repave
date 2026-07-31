package repave

import (
	"fmt"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

// MaxUpgradePlanPaths caps path lists stored on GoldenPathRepo status.
const MaxUpgradePlanPaths = 20

// BuildUpgradePlan shapes a plan-upgrade result for GoldenPathRepo status.
func BuildUpgradePlan(result PlanResult) (*repavev1beta1.UpgradePlan, string) {
	summary := result.Summary
	if summary == "" {
		summary = fmt.Sprintf(
			"%d file(s) differ for blueprint %s@%s",
			result.ChangedFileCount,
			result.BlueprintName,
			result.BlueprintVersion,
		)
	}
	return &repavev1beta1.UpgradePlan{
		ChangedFileCount: result.ChangedFileCount,
		BlueprintName:    result.BlueprintName,
		BlueprintVersion: result.BlueprintVersion,
		Added:            TruncatePaths(result.Added, MaxUpgradePlanPaths),
		Modified:         TruncatePaths(result.Modified, MaxUpgradePlanPaths),
		Removed:          TruncatePaths(result.Removed, MaxUpgradePlanPaths),
		Summary:          summary,
	}, summary
}

// TruncatePaths returns at most limit entries from paths.
func TruncatePaths(paths []string, limit int) []string {
	if len(paths) <= limit {
		return paths
	}
	return paths[:limit]
}
