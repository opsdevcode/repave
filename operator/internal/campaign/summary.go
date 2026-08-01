package campaign

import (
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/remediation"
	"github.com/opsdevcode/repave/operator/internal/status"
)

// FleetSummary aggregates drift SLO signals for matched GoldenPathRepos.
type FleetSummary struct {
	OpenPRCount                   int32
	OutOfDateCount                int32
	OldestDriftAgeSeconds         int64
	AverageRemediationMTTRSeconds int64
	ConsecutiveGateFailures       int32
}

// SummarizeMatchedRepos computes fleet SLO stats for repos governed by the campaign.
func SummarizeMatchedRepos(
	uc *repavev1beta1.UpgradeCampaign,
	repos []repavev1beta1.GoldenPathRepo,
	now time.Time,
) (FleetSummary, error) {
	var summary FleetSummary
	var mttrTotal int64
	var mttrCount int64

	for i := range repos {
		repo := &repos[i]
		matched, err := MatchGoldenPathRepo(uc, repo)
		if err != nil {
			return FleetSummary{}, err
		}
		if !matched {
			continue
		}

		if repo.Status.Phase == repavev1beta1.GoldenPathRepoPhaseOutOfDate {
			summary.OutOfDateCount++
			if age := driftAgeSeconds(repo, now); age > summary.OldestDriftAgeSeconds {
				summary.OldestDriftAgeSeconds = age
			}
		}

		if repo.Status.RemediationPR != nil &&
			repo.Status.RemediationPR.State == remediation.PRStateOpen {
			summary.OpenPRCount++
		}

		if failure, _ := latestRemediationFailure(repo); failure {
			summary.ConsecutiveGateFailures++
		}

		if mttr := completedRemediationMTTRSeconds(repo, now); mttr > 0 {
			mttrTotal += mttr
			mttrCount++
		}
	}

	if mttrCount > 0 {
		summary.AverageRemediationMTTRSeconds = mttrTotal / mttrCount
	}
	return summary, nil
}

func driftAgeSeconds(repo *repavev1beta1.GoldenPathRepo, now time.Time) int64 {
	detectedAt := DriftDetectedTime(repo)
	if detectedAt.IsZero() {
		return 0
	}
	age := now.Sub(detectedAt)
	if age < 0 {
		return 0
	}
	return int64(age.Seconds())
}

// DriftDetectedTime returns when drift was first observed for a repo.
func DriftDetectedTime(repo *repavev1beta1.GoldenPathRepo) time.Time {
	if repo.Status.DriftDetectedAt != nil {
		return repo.Status.DriftDetectedAt.Time
	}
	for _, cond := range repo.Status.Conditions {
		if cond.Type == status.ConditionDriftDetected && cond.Status == metav1.ConditionTrue {
			return cond.LastTransitionTime.Time
		}
	}
	return time.Time{}
}

func completedRemediationMTTRSeconds(repo *repavev1beta1.GoldenPathRepo, now time.Time) int64 {
	if repo.Status.Phase != repavev1beta1.GoldenPathRepoPhaseReady {
		return 0
	}
	detectedAt := DriftDetectedTime(repo)
	if detectedAt.IsZero() {
		return 0
	}
	for _, cond := range repo.Status.Conditions {
		if cond.Type != status.ConditionDriftDetected {
			continue
		}
		if cond.Status != metav1.ConditionFalse || cond.Reason != status.ReasonPinsAligned {
			continue
		}
		resolvedAt := cond.LastTransitionTime.Time
		if resolvedAt.IsZero() || resolvedAt.Before(detectedAt) {
			return 0
		}
		return int64(resolvedAt.Sub(detectedAt).Seconds())
	}
	_ = now
	return 0
}

func latestRemediationFailure(repo *repavev1beta1.GoldenPathRepo) (bool, string) {
	for _, cond := range repo.Status.Conditions {
		if cond.Type != status.ConditionRemediationPR {
			continue
		}
		if cond.Status == metav1.ConditionFalse && cond.Reason == status.ReasonRemediationFailed {
			return true, cond.Message
		}
	}
	return false, ""
}
