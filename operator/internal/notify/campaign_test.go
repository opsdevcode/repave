package notify

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
)

func TestSendCampaignEventPostsSummary(t *testing.T) {
	var received string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		received = string(body)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	t.Setenv("REPAVE_NOTIFY_WEBHOOK_URL", srv.URL)
	t.Setenv("REPAVE_OPERATOR_NOTIFY_EVENTS", EventCampaignSummary)

	uc := &repavev1beta1.UpgradeCampaign{
		ObjectMeta: metav1.ObjectMeta{Name: "fleet", Namespace: "default"},
		Status: repavev1beta1.UpgradeCampaignStatus{
			Phase: repavev1beta1.UpgradeCampaignPhaseActive,
		},
	}
	SendCampaignEvent(
		context.Background(),
		EventCampaignSummary,
		uc,
		campaign.FleetSummary{OutOfDateCount: 2, OpenPRCount: 1, OldestDriftAgeSeconds: 600},
		"2 repos out of date",
	)

	if !strings.Contains(received, `"event":"campaign_summary"`) {
		t.Fatalf("expected campaign_summary payload, got %q", received)
	}
	if !strings.Contains(received, `"out_of_date_count":2`) {
		t.Fatalf("expected out_of_date_count in payload, got %q", received)
	}
}

func TestLoadConfigIncludesCampaignEventsByDefault(t *testing.T) {
	t.Setenv("REPAVE_NOTIFY_WEBHOOK_URL", "https://example.com/hook")
	t.Setenv("REPAVE_OPERATOR_NOTIFY_EVENTS", "")

	cfg := LoadConfig()
	if _, ok := cfg.Events[EventCampaignSummary]; !ok {
		t.Fatalf("missing %s", EventCampaignSummary)
	}
}
