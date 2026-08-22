package controller

import (
	"context"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
)

func TestEnqueueUpgradeCampaignsForGoldenPathRepoUsesLabel(t *testing.T) {
	r := &UpgradeCampaignReconciler{}
	gpr := &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "payments",
			Namespace: "platform",
			Labels:    map[string]string{campaign.UpgradeCampaignLabel: "fleet"},
		},
	}
	got := r.enqueueUpgradeCampaignsForGoldenPathRepo(context.Background(), gpr)
	if len(got) != 1 {
		t.Fatalf("expected 1 request, got %d", len(got))
	}
	if got[0].Namespace != "platform" || got[0].Name != "fleet" {
		t.Fatalf("unexpected request: %+v", got[0])
	}
}
