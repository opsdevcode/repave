package github_test

import (
	"net/http"
	"strconv"
	"testing"
	"time"

	"github.com/opsdevcode/repave/operator/internal/github"
)

func TestRateLimitTrackerUpdatesFromHeaders(t *testing.T) {
	t.Parallel()
	github.ResetRateLimitTracker()
	tracker := github.DefaultRateLimitTracker()

	resetAt := time.Now().Add(30 * time.Second).Unix()
	headers := http.Header{}
	headers.Set("X-RateLimit-Remaining", "10")
	headers.Set("X-RateLimit-Limit", "5000")
	headers.Set("X-RateLimit-Reset", formatUnix(resetAt))

	tracker.UpdateFromHeaders(headers, "12345")
	state, ok := tracker.Snapshot("12345")
	if !ok {
		t.Fatal("expected snapshot")
	}
	if state.Remaining != 10 {
		t.Fatalf("expected remaining 10, got %d", state.Remaining)
	}
	if !state.Low(50) {
		t.Fatal("expected low remaining")
	}
}

func TestRateLimitGateBlocksWhenRemainingLow(t *testing.T) {
	github.ResetRateLimitTracker()
	t.Setenv("REPAVE_GITHUB_RATE_LIMIT_MIN_REMAINING", "50")

	resetAt := time.Now().Add(time.Minute).Unix()
	headers := http.Header{}
	headers.Set("X-RateLimit-Remaining", "1")
	headers.Set("X-RateLimit-Reset", formatUnix(resetAt))
	github.DefaultRateLimitTracker().UpdateFromHeaders(headers, "default")

	blocked, message := github.RateLimitGate()
	if !blocked {
		t.Fatal("expected rate limit gate to block")
	}
	if message == "" {
		t.Fatal("expected message")
	}
}

func TestRateLimitGateAllowsWhenUnknown(t *testing.T) {
	github.ResetRateLimitTracker()
	blocked, message := github.RateLimitGate()
	if blocked || message != "" {
		t.Fatalf("expected open gate, got blocked=%v message=%q", blocked, message)
	}
}

func TestBackoffSecondsUsesRetryAfter(t *testing.T) {
	t.Parallel()
	delay := github.BackoffSeconds("12", 0)
	if delay != 12*time.Second {
		t.Fatalf("expected 12s, got %v", delay)
	}
}

func formatUnix(value int64) string {
	return strconv.FormatInt(value, 10)
}
