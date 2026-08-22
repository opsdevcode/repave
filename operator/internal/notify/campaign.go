package notify

import (
	"context"
	"fmt"
	"strings"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
)

// SendCampaignEvent delivers a webhook notification for an UpgradeCampaign event.
func SendCampaignEvent(
	ctx context.Context,
	event string,
	uc *repavev1beta1.UpgradeCampaign,
	summary campaign.FleetSummary,
	message string,
) {
	cfg := LoadConfig()
	if !cfg.Enabled {
		return
	}
	if _, ok := cfg.Events[event]; !ok {
		return
	}

	maxConcurrent := campaign.DefaultMaxConcurrentPRs
	if uc.Spec.MaxConcurrentPRs != nil && *uc.Spec.MaxConcurrentPRs > 0 {
		maxConcurrent = *uc.Spec.MaxConcurrentPRs
	}

	payload := CampaignPayload{
		Event:                         event,
		Namespace:                     uc.Namespace,
		Campaign:                      uc.Name,
		Phase:                         uc.Status.Phase,
		OpenPRCount:                   summary.OpenPRCount,
		OutOfDateCount:                summary.OutOfDateCount,
		OldestDriftAgeSeconds:         summary.OldestDriftAgeSeconds,
		AverageRemediationMTTRSeconds: summary.AverageRemediationMTTRSeconds,
		MaxConcurrentPRs:              maxConcurrent,
		Message:                       message,
	}
	text := formatCampaignText(payload)
	PostJSON(ctx, cfg.URLs, payload, text)
}

// CampaignPayload is the webhook body for upgrade campaign events.
type CampaignPayload struct {
	Event                         string `json:"event"`
	Namespace                     string `json:"namespace"`
	Campaign                      string `json:"campaign"`
	Phase                         string `json:"phase"`
	OpenPRCount                   int32  `json:"open_pr_count"`
	OutOfDateCount                int32  `json:"out_of_date_count"`
	OldestDriftAgeSeconds         int64  `json:"oldest_drift_age_seconds"`
	AverageRemediationMTTRSeconds int64  `json:"average_remediation_mttr_seconds"`
	MaxConcurrentPRs              int32  `json:"max_concurrent_prs"`
	Message                       string `json:"message"`
}

func formatCampaignText(p CampaignPayload) string {
	lines := []string{
		"*" + p.Event + "*",
		fmt.Sprintf("UpgradeCampaign: `%s/%s`", p.Namespace, p.Campaign),
		fmt.Sprintf("Phase: %s", p.Phase),
		fmt.Sprintf(
			"Fleet: %d out of date, %d open PRs (cap %d)",
			p.OutOfDateCount,
			p.OpenPRCount,
			p.MaxConcurrentPRs,
		),
	}
	if p.OldestDriftAgeSeconds > 0 {
		lines = append(lines, fmt.Sprintf("Oldest drift age: %ds", p.OldestDriftAgeSeconds))
	}
	if p.AverageRemediationMTTRSeconds > 0 {
		lines = append(lines, fmt.Sprintf("Avg remediation MTTR: %ds", p.AverageRemediationMTTRSeconds))
	}
	if strings.TrimSpace(p.Message) != "" {
		lines = append(lines, p.Message)
	}
	return strings.Join(lines, "\n")
}
