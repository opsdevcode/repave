package campaign_test

import (
	"testing"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
	"github.com/opsdevcode/repave/operator/internal/remediation"
	"github.com/opsdevcode/repave/operator/internal/status"
)

func TestSummarizeMatchedReposCountsDriftAndOpenPRs(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 31, 12, 0, 0, 0, time.UTC)
	driftStart := metav1.NewTime(now.Add(-2 * time.Hour))
	uc := &repavev1beta1.UpgradeCampaign{
		ObjectMeta: metav1.ObjectMeta{Name: "fleet"},
		Spec:       repavev1beta1.UpgradeCampaignSpec{},
	}
	repos := []repavev1beta1.GoldenPathRepo{
		{
			ObjectMeta: metav1.ObjectMeta{
				Labels: map[string]string{campaign.UpgradeCampaignLabel: "fleet"},
			},
			Status: repavev1beta1.GoldenPathRepoStatus{
				Phase:           repavev1beta1.GoldenPathRepoPhaseOutOfDate,
				DriftDetectedAt: &driftStart,
				RemediationPR: &repavev1beta1.RemediationPRStatus{
					State: remediation.PRStateOpen,
				},
			},
		},
		{
			ObjectMeta: metav1.ObjectMeta{
				Labels: map[string]string{campaign.UpgradeCampaignLabel: "fleet"},
			},
			Status: repavev1beta1.GoldenPathRepoStatus{
				Phase: repavev1beta1.GoldenPathRepoPhaseReady,
				Conditions: []metav1.Condition{
					{
						Type:               status.ConditionDriftDetected,
						Status:             metav1.ConditionFalse,
						Reason:             status.ReasonPinsAligned,
						LastTransitionTime: metav1.NewTime(now.Add(-30 * time.Minute)),
					},
				},
				DriftDetectedAt: func() *metav1.Time {
					ts := metav1.NewTime(now.Add(-90 * time.Minute))
					return &ts
				}(),
			},
		},
	}

	summary, err := campaign.SummarizeMatchedRepos(uc, repos, now)
	if err != nil {
		t.Fatalf("SummarizeMatchedRepos: %v", err)
	}
	if summary.OutOfDateCount != 1 {
		t.Fatalf("expected 1 out of date, got %d", summary.OutOfDateCount)
	}
	if summary.OpenPRCount != 1 {
		t.Fatalf("expected 1 open PR, got %d", summary.OpenPRCount)
	}
	if summary.OldestDriftAgeSeconds != 7200 {
		t.Fatalf("expected oldest drift 7200s, got %d", summary.OldestDriftAgeSeconds)
	}
}

func TestDriftDetectedTimeUsesStatusTimestamp(t *testing.T) {
	t.Parallel()
	ts := metav1.Now()
	repo := &repavev1beta1.GoldenPathRepo{
		Status: repavev1beta1.GoldenPathRepoStatus{
			DriftDetectedAt: &ts,
		},
	}
	got := campaign.DriftDetectedTime(repo)
	if !got.Equal(ts.Time) {
		t.Fatalf("expected %v, got %v", ts.Time, got)
	}
}
