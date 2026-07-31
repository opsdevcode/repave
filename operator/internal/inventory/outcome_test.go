package inventory

import (
	"errors"
	"fmt"
	"testing"
	"time"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/drift"
	"github.com/opsdevcode/repave/operator/internal/status"
)

func TestClassifyMaterializeError(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name       string
		err        error
		wantReason string
		wantRetry  time.Duration
	}{
		{
			name:       "unsupported",
			err:        ErrRemoteRepoNotSupported,
			wantReason: status.ReasonRemoteRepoUnsupported,
		},
		{
			name:       "fetch failed",
			err:        fmt.Errorf("wrap: %w", ErrRemoteFetchFailed),
			wantReason: status.ReasonRemoteFetchFailed,
			wantRetry:  RemoteFetchRetry,
		},
		{
			name:       "default",
			err:        errors.New("read failed"),
			wantReason: status.ReasonProvenanceReadFailed,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := ClassifyMaterializeError(tc.err)
			if got.Reason != tc.wantReason {
				t.Fatalf("Reason = %q, want %q", got.Reason, tc.wantReason)
			}
			if got.RetryAfter != tc.wantRetry {
				t.Fatalf("RetryAfter = %v, want %v", got.RetryAfter, tc.wantRetry)
			}
		})
	}
}

func TestEvaluateObservation(t *testing.T) {
	t.Parallel()

	desired := drift.PinSet{
		BlueprintName:    "mod",
		BlueprintVersion: "2.0.0",
	}
	observed := drift.PinSet{
		BlueprintName:    "mod",
		BlueprintVersion: "1.0.0",
	}
	spec := repavev1beta1.GoldenPathRepoSpec{LocalPath: "/tmp/repo"}

	driftResult := EvaluateObservation(
		spec,
		desired,
		observed,
		repavev1beta1.GoldenPathRepoPhaseReady,
	)
	if driftResult.Phase != repavev1beta1.GoldenPathRepoPhaseOutOfDate {
		t.Fatalf("Phase = %q, want OutOfDate", driftResult.Phase)
	}
	if !driftResult.NotifyDrift {
		t.Fatal("NotifyDrift = false, want true on first drift")
	}

	driftResult = EvaluateObservation(
		spec,
		desired,
		observed,
		repavev1beta1.GoldenPathRepoPhaseOutOfDate,
	)
	if driftResult.NotifyDrift {
		t.Fatal("NotifyDrift = true, want false when already OutOfDate")
	}

	aligned := EvaluateObservation(
		spec,
		desired,
		desired,
		repavev1beta1.GoldenPathRepoPhaseOutOfDate,
	)
	if aligned.Phase != repavev1beta1.GoldenPathRepoPhaseReady {
		t.Fatalf("Phase = %q, want Ready", aligned.Phase)
	}
}

func TestDisplayLocation(t *testing.T) {
	t.Parallel()

	if got := DisplayLocation(repavev1beta1.GoldenPathRepoSpec{LocalPath: "/a"}); got != "/a" {
		t.Fatalf("DisplayLocation(local) = %q", got)
	}
	if got := DisplayLocation(repavev1beta1.GoldenPathRepoSpec{RepoURL: "https://x"}); got != "https://x" {
		t.Fatalf("DisplayLocation(remote) = %q", got)
	}
}
