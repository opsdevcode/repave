package campaign_test

import (
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
	"github.com/opsdevcode/repave/operator/internal/remediation"
)

func TestMatchGoldenPathRepoRequiresCampaignLabel(t *testing.T) {
	t.Parallel()
	uc := &repavev1beta1.UpgradeCampaign{
		ObjectMeta: metav1.ObjectMeta{Name: "fleet"},
		Spec:       repavev1beta1.UpgradeCampaignSpec{},
	}
	repo := &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Labels: map[string]string{campaign.UpgradeCampaignLabel: "other"},
		},
	}
	matched, err := campaign.MatchGoldenPathRepo(uc, repo)
	if err != nil {
		t.Fatalf("MatchGoldenPathRepo: %v", err)
	}
	if matched {
		t.Fatal("expected no match without campaign label")
	}
}

func TestMatchGoldenPathRepoWithLabel(t *testing.T) {
	t.Parallel()
	max := int32(2)
	uc := &repavev1beta1.UpgradeCampaign{
		ObjectMeta: metav1.ObjectMeta{Name: "fleet"},
		Spec: repavev1beta1.UpgradeCampaignSpec{
			MaxConcurrentPRs: &max,
		},
	}
	repo := &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Labels: map[string]string{campaign.UpgradeCampaignLabel: "fleet"},
		},
		Spec: repavev1beta1.GoldenPathRepoSpec{
			DesiredPins: repavev1beta1.DesiredPins{
				BlueprintName: "terraform-minimal",
			},
		},
	}
	matched, err := campaign.MatchGoldenPathRepo(uc, repo)
	if err != nil {
		t.Fatalf("MatchGoldenPathRepo: %v", err)
	}
	if !matched {
		t.Fatal("expected match")
	}
}

func TestDefaultMaxConcurrentPRs(t *testing.T) {
	t.Parallel()
	if campaign.DefaultMaxConcurrentPRs != 5 {
		t.Fatalf("expected default max 5, got %d", campaign.DefaultMaxConcurrentPRs)
	}
	_ = remediation.PRStateOpen
}
