package repave

import "testing"

func TestBuildUpgradePlan(t *testing.T) {
	t.Parallel()

	plan, summary := BuildUpgradePlan(PlanResult{
		BlueprintName:    "mod",
		BlueprintVersion: "1.0.0",
		ChangedFileCount: 2,
		Added:            []string{"a", "b"},
	})
	if plan.BlueprintName != "mod" || plan.ChangedFileCount != 2 {
		t.Fatalf("unexpected plan: %+v", plan)
	}
	if summary == "" {
		t.Fatal("summary is empty")
	}
}

func TestTruncatePaths(t *testing.T) {
	t.Parallel()

	paths := []string{"a", "b", "c"}
	if got := TruncatePaths(paths, 5); len(got) != 3 {
		t.Fatalf("TruncatePaths(3,5) len = %d", len(got))
	}
	if got := TruncatePaths(paths, 2); len(got) != 2 {
		t.Fatalf("TruncatePaths(3,2) len = %d", len(got))
	}
}
