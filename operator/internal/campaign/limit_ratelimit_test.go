package campaign_test

import (
	"context"
	"net/http"
	"strconv"
	"testing"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
	"github.com/opsdevcode/repave/operator/internal/campaign"
	"github.com/opsdevcode/repave/operator/internal/github"
	"github.com/opsdevcode/repave/operator/internal/status"
)

func TestEvaluateRemediationBlocksWhenRateLimitLow(t *testing.T) {
	github.ResetRateLimitTracker()
	t.Setenv("REPAVE_GITHUB_RATE_LIMIT_MIN_REMAINING", "50")

	resetAt := time.Now().Add(time.Minute).Unix()
	headers := http.Header{}
	headers.Set("X-RateLimit-Remaining", "3")
	headers.Set("X-RateLimit-Reset", strconv.FormatInt(resetAt, 10))
	github.DefaultRateLimitTracker().UpdateFromHeaders(headers, "default")

	repo := &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "payments",
			Namespace: "default",
		},
		Spec: repavev1beta1.GoldenPathRepoSpec{
			DesiredPins: repavev1beta1.DesiredPins{BlueprintName: "app"},
		},
	}
	scheme := runtime.NewScheme()
	utilruntime.Must(repavev1beta1.AddToScheme(scheme))
	c := fake.NewClientBuilder().WithScheme(scheme).Build()

	decision, err := campaign.EvaluateRemediation(context.Background(), c, repo)
	if err != nil {
		t.Fatalf("EvaluateRemediation: %v", err)
	}
	if decision.Allowed {
		t.Fatal("expected remediation blocked by rate limit")
	}
	if decision.Reason != status.ReasonRemediationRateLimited {
		t.Fatalf("expected %s, got %s", status.ReasonRemediationRateLimited, decision.Reason)
	}
}
