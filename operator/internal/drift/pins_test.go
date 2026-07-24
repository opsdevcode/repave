package drift_test

import (
	"testing"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/drift"
)

func TestPinsDiffer(t *testing.T) {
	desired := drift.PinsFromDesired(repavev1alpha1.GoldenPathRepoSpec{
		DesiredPins: repavev1alpha1.DesiredPins{
			BlueprintName:    "terraform-module-generic",
			BlueprintVersion: "0.1.0",
			StandardSource:   "examples/standards",
			StandardVersion:  "0.4.0",
		},
	})
	observed := desired
	if drift.PinsDiffer(desired, observed) {
		t.Fatal("expected identical pins not to differ")
	}

	observed.BlueprintVersion = "0.2.0"
	if !drift.PinsDiffer(desired, observed) {
		t.Fatal("expected version bump to differ")
	}
}
