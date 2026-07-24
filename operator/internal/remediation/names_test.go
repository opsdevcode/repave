package remediation

import "testing"

func TestUpgradeBranchName(t *testing.T) {
	got := UpgradeBranchName("repave/upgrade", "terraform-module-generic", "0.8.0")
	want := "repave/upgrade/terraform-module-generic-0.8.0"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}
