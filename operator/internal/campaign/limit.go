package campaign

import (
	"context"
	"fmt"
	"strings"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/labels"
	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/github"
	"github.com/opsdevcode/repave/operator/internal/remediation"
	"github.com/opsdevcode/repave/operator/internal/status"
)

const (
	UpgradeCampaignLabel = "repave.dev/upgrade-campaign"

	DefaultMaxConcurrentPRs int32 = 5
)

// RemediationDecision reports whether a remediation PR may open under campaign policy.
type RemediationDecision struct {
	Allowed bool
	Reason  string
	Message string
}

// EvaluateRemediation checks campaign pause, capacity, and stop conditions for a repo.
func EvaluateRemediation(
	ctx context.Context,
	c client.Client,
	repo *repavev1beta1.GoldenPathRepo,
) (RemediationDecision, error) {
	if blocked, message := github.RateLimitGate(); blocked {
		return RemediationDecision{
			Allowed: false,
			Reason:  status.ReasonRemediationRateLimited,
			Message: message,
		}, nil
	}

	campaignName := strings.TrimSpace(repo.Labels[UpgradeCampaignLabel])
	if campaignName == "" {
		return RemediationDecision{Allowed: true}, nil
	}

	var campaign repavev1beta1.UpgradeCampaign
	if err := c.Get(ctx, client.ObjectKey{Namespace: repo.Namespace, Name: campaignName}, &campaign); err != nil {
		return RemediationDecision{
			Allowed: false,
			Reason:  status.ReasonRemediationSkipped,
			Message: fmt.Sprintf("upgrade campaign %q not found", campaignName),
		}, client.IgnoreNotFound(err)
	}

	if campaign.Spec.Paused || campaign.Status.Phase == repavev1beta1.UpgradeCampaignPhasePaused {
		return RemediationDecision{
			Allowed: false,
			Reason:  status.ReasonRemediationCampaignPaused,
			Message: fmt.Sprintf("upgrade campaign %q is paused", campaignName),
		}, nil
	}
	if campaign.Status.Phase == repavev1beta1.UpgradeCampaignPhaseStopped {
		return RemediationDecision{
			Allowed: false,
			Reason:  status.ReasonRemediationCampaignStopped,
			Message: fmt.Sprintf("upgrade campaign %q is stopped after gate failures", campaignName),
		}, nil
	}

	if campaign.Spec.BlueprintName != "" {
		desiredName := repo.Spec.DesiredPins.BlueprintName
		if repo.Spec.BlueprintRef != nil && repo.Spec.BlueprintRef.Name != "" {
			desiredName = repo.Spec.BlueprintRef.Name
		}
		if desiredName != campaign.Spec.BlueprintName {
			return RemediationDecision{Allowed: true}, nil
		}
	}

	maxOpen := DefaultMaxConcurrentPRs
	if campaign.Spec.MaxConcurrentPRs != nil && *campaign.Spec.MaxConcurrentPRs > 0 {
		maxOpen = *campaign.Spec.MaxConcurrentPRs
	}

	openCount, err := countOpenRemediationPRs(ctx, c, &campaign, repo.Name)
	if err != nil {
		return RemediationDecision{}, err
	}
	if openCount >= maxOpen {
		return RemediationDecision{
			Allowed: false,
			Reason:  status.ReasonRemediationCampaignCapacity,
			Message: fmt.Sprintf(
				"upgrade campaign %q at capacity (%d/%d open remediation PRs)",
				campaignName,
				openCount,
				maxOpen,
			),
		}, nil
	}

	return RemediationDecision{Allowed: true}, nil
}

func countOpenRemediationPRs(
	ctx context.Context,
	c client.Client,
	campaign *repavev1beta1.UpgradeCampaign,
	excludeRepo string,
) (int32, error) {
	var repos repavev1beta1.GoldenPathRepoList
	if err := c.List(ctx, &repos, client.InNamespace(campaign.Namespace)); err != nil {
		return 0, err
	}

	selector, err := selectorForCampaign(campaign)
	if err != nil {
		return 0, err
	}

	requiredLabel := UpgradeCampaignLabel
	requiredValue := campaign.Name
	var count int32
	for i := range repos.Items {
		repo := &repos.Items[i]
		if repo.Name == excludeRepo {
			continue
		}
		if repo.Labels[requiredLabel] != requiredValue {
			continue
		}
		if !selector.Matches(labels.Set(repo.Labels)) {
			continue
		}
		if repo.Status.RemediationPR != nil && repo.Status.RemediationPR.State == remediation.PRStateOpen {
			count++
		}
	}
	return count, nil
}

// MatchGoldenPathRepo reports whether a repo belongs to the campaign selector and label.
func MatchGoldenPathRepo(campaign *repavev1beta1.UpgradeCampaign, repo *repavev1beta1.GoldenPathRepo) (bool, error) {
	if repo.Labels[UpgradeCampaignLabel] != campaign.Name {
		return false, nil
	}
	selector, err := selectorForCampaign(campaign)
	if err != nil {
		return false, err
	}
	if !selector.Matches(labels.Set(repo.Labels)) {
		return false, nil
	}
	if campaign.Spec.BlueprintName != "" {
		desiredName := repo.Spec.DesiredPins.BlueprintName
		if repo.Spec.BlueprintRef != nil && repo.Spec.BlueprintRef.Name != "" {
			desiredName = repo.Spec.BlueprintRef.Name
		}
		if desiredName != campaign.Spec.BlueprintName {
			return false, nil
		}
	}
	return true, nil
}

func selectorForCampaign(campaign *repavev1beta1.UpgradeCampaign) (labels.Selector, error) {
	if campaign.Spec.Selector == nil {
		return labels.Everything(), nil
	}
	return metav1.LabelSelectorAsSelector(campaign.Spec.Selector)
}
