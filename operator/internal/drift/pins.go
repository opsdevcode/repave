package drift

import repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"

// PinSet holds blueprint and standard identity for comparison.
type PinSet struct {
	BlueprintName    string
	BlueprintVersion string
	StandardSource   string
	StandardVersion  string
}

// PinsFromDesired extracts pins from a GoldenPathRepo spec.
func PinsFromDesired(spec repavev1alpha1.GoldenPathRepoSpec) PinSet {
	return PinSet{
		BlueprintName:    spec.DesiredPins.BlueprintName,
		BlueprintVersion: spec.DesiredPins.BlueprintVersion,
		StandardSource:   spec.DesiredPins.StandardSource,
		StandardVersion:  spec.DesiredPins.StandardVersion,
	}
}

// PinsDiffer reports whether desired and observed pins are not equal.
func PinsDiffer(desired, observed PinSet) bool {
	return desired != observed
}
