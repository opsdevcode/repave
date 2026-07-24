package repave

import "testing"

func TestStaticPlanUpgraderReturnsResult(t *testing.T) {
	upgrader := &StaticPlanUpgrader{
		Result: PlanResult{ChangedFileCount: 1, Summary: "ok"},
	}
	got, err := upgrader.PlanUpgrade(t.Context(), Config{}, "/tmp/module", "terraform-module-generic")
	if err != nil {
		t.Fatalf("PlanUpgrade: %v", err)
	}
	if got.ChangedFileCount != 1 {
		t.Fatalf("got count %d", got.ChangedFileCount)
	}
	if upgrader.Calls != 1 {
		t.Fatalf("calls = %d", upgrader.Calls)
	}
}
