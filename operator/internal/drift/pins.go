package drift

import (
	"fmt"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
)

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

// Validate ensures all pin fields are non-empty.
func (p PinSet) Validate() error {
	if p.BlueprintName == "" {
		return fmt.Errorf("blueprint name is required")
	}
	if p.BlueprintVersion == "" {
		return fmt.Errorf("blueprint version is required")
	}
	if p.StandardSource == "" {
		return fmt.Errorf("standard source is required")
	}
	if p.StandardVersion == "" {
		return fmt.Errorf("standard version is required")
	}
	return nil
}

// ToObserved converts pins to GoldenPathRepo status fields.
func (p PinSet) ToObserved() repavev1alpha1.ObservedPins {
	return repavev1alpha1.ObservedPins{
		BlueprintName:    p.BlueprintName,
		BlueprintVersion: p.BlueprintVersion,
		StandardSource:   p.StandardSource,
		StandardVersion:  p.StandardVersion,
	}
}

// PinSetFromObserved reads status observed pins.
func PinSetFromObserved(o repavev1alpha1.ObservedPins) PinSet {
	return PinSet{
		BlueprintName:    o.BlueprintName,
		BlueprintVersion: o.BlueprintVersion,
		StandardSource:   o.StandardSource,
		StandardVersion:  o.StandardVersion,
	}
}
