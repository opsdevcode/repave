package inventory

import (
	"errors"
	"fmt"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/provenance"
)

// ErrRemoteRepoNotSupported is returned until git clone inventory lands (slice 2+).
var ErrRemoteRepoNotSupported = errors.New("repoURL inventory requires git clone (not implemented)")

// ObservePins reads observed blueprint/standard pins from the registered repository.
func ObservePins(spec repavev1alpha1.GoldenPathRepoSpec) (drift.PinSet, error) {
	switch {
	case spec.LocalPath != "":
		return provenance.ReadPinsFromRepoRoot(spec.LocalPath)
	case spec.RepoURL != "":
		return drift.PinSet{}, fmt.Errorf("%w", ErrRemoteRepoNotSupported)
	default:
		return drift.PinSet{}, fmt.Errorf("spec.repoURL or spec.localPath is required")
	}
}

// EvaluateDesiredObserved compares desired spec pins to observed repo pins.
func EvaluateDesiredObserved(desired, observed drift.PinSet) (outOfDate bool) {
	return drift.PinsDiffer(desired, observed)
}
