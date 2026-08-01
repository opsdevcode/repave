package conventions_test

import (
	"os"
	"testing"

	"github.com/opsdevcode/repave/operator/internal/conventions"
)

func TestLoadPullRequestDefaults(t *testing.T) {
	t.Setenv("REPAVE_PR_BRANCH_PREFIX_UPGRADE", "acme/upgrade")
	t.Setenv("REPAVE_PR_LABELS", "repave,custom")
	t.Setenv("REPAVE_PR_EVIDENCE_CHECKLIST", "false")

	defaults := conventions.LoadPullRequestDefaults()
	if defaults.BranchPrefixUpgrade != "acme/upgrade" {
		t.Fatalf("branch prefix: %q", defaults.BranchPrefixUpgrade)
	}
	if len(defaults.Labels) != 2 || defaults.Labels[0] != "repave" {
		t.Fatalf("labels: %#v", defaults.Labels)
	}
	if defaults.EvidenceChecklist {
		t.Fatal("expected evidence checklist disabled")
	}
}

func TestUpgradeBodyIncludesEvidenceChecklist(t *testing.T) {
	body := conventions.UpgradeBody("", "bp", "1.0.0", "2.0.0", "")
	if body == "" {
		t.Fatal("expected body")
	}
	os.Unsetenv("REPAVE_PR_EVIDENCE_CHECKLIST")
}
