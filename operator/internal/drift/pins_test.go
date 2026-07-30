package drift_test

import (
	"testing"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/drift"
)

func TestPinsDiffer(t *testing.T) {
	desired := drift.PinsFromDesired(repavev1beta1.GoldenPathRepoSpec{
		DesiredPins: repavev1beta1.DesiredPins{
			BlueprintName:    "terraform-module-generic",
			BlueprintVersion: "0.9.0",
			StandardSource:   "standards/terraform-standards",
			StandardVersion:  "1.1.0",
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
