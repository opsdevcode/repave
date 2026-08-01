package inventory

import (
	"errors"
	"fmt"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/provenance"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// RemoteFetchRetry backs off after a transient clone failure (network, auth, missing ref).
const RemoteFetchRetry = 2 * time.Minute

// MaterializeFailure classifies a materialize error for status and requeue policy.
type MaterializeFailure struct {
	Reason     string
	Message    string
	RetryAfter time.Duration
}

// ClassifyMaterializeError maps inventory materialize errors to failure metadata.
func ClassifyMaterializeError(err error) MaterializeFailure {
	reason := status.ReasonProvenanceReadFailed
	retryAfter := time.Duration(0)
	switch {
	case errors.Is(err, ErrRemoteRepoNotSupported):
		reason = status.ReasonRemoteRepoUnsupported
	case errors.Is(err, ErrRemoteFetchFailed):
		reason = status.ReasonRemoteFetchFailed
		retryAfter = RemoteFetchRetry
	}
	return MaterializeFailure{
		Reason:     reason,
		Message:    err.Error(),
		RetryAfter: retryAfter,
	}
}

// ClassifyProvenanceError maps provenance read failures to operator status reasons.
func ClassifyProvenanceError(err error) MaterializeFailure {
	if errors.Is(err, provenance.ErrProvenanceMissing) {
		return MaterializeFailure{
			Reason: status.ReasonProvenanceMissing,
			Message: fmt.Sprintf(
				"repository is missing required %s at repo root; regenerate with repave or run repave import",
				provenance.DefaultFilename,
			),
		}
	}
	return MaterializeFailure{
		Reason:  status.ReasonProvenanceReadFailed,
		Message: err.Error(),
	}
}

// ObservationResult is the inventory outcome before status is patched.
type ObservationResult struct {
	Observed      drift.PinSet
	Phase         repavev1beta1.GoldenPathRepoPhase
	Message       string
	DriftDetected metav1.ConditionStatus
	DriftReason   string
	ReadyReason   string
	NotifyDrift   bool
}

// EvaluateObservation compares desired pins to observed repo pins.
func EvaluateObservation(
	spec repavev1beta1.GoldenPathRepoSpec,
	desired drift.PinSet,
	observed drift.PinSet,
	currentPhase repavev1beta1.GoldenPathRepoPhase,
) ObservationResult {
	location := DisplayLocation(spec)
	if EvaluateDesiredObserved(desired, observed) {
		msg := fmt.Sprintf(
			"observed pins differ from desired (blueprint %s@%s vs %s@%s)",
			desired.BlueprintName,
			desired.BlueprintVersion,
			observed.BlueprintName,
			observed.BlueprintVersion,
		)
		return ObservationResult{
			Observed:      observed,
			Phase:         repavev1beta1.GoldenPathRepoPhaseOutOfDate,
			Message:       msg,
			DriftDetected: metav1.ConditionTrue,
			DriftReason:   status.ReasonPinsDrift,
			ReadyReason:   status.ReasonPinsDrift,
			NotifyDrift:   currentPhase != repavev1beta1.GoldenPathRepoPhaseOutOfDate,
		}
	}

	msg := fmt.Sprintf("pins aligned for %q", location)
	return ObservationResult{
		Observed:      observed,
		Phase:         repavev1beta1.GoldenPathRepoPhaseReady,
		Message:       msg,
		DriftDetected: metav1.ConditionFalse,
		DriftReason:   status.ReasonPinsAligned,
		ReadyReason:   status.ReasonPinsAligned,
	}
}

// DisplayLocation returns the user-facing repo location from spec.
func DisplayLocation(spec repavev1beta1.GoldenPathRepoSpec) string {
	if spec.LocalPath != "" {
		return spec.LocalPath
	}
	return spec.RepoURL
}
