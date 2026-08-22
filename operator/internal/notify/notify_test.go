package notify

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestLoadConfigDefaultsEventsWhenURLsSet(t *testing.T) {
	t.Setenv("REPAVE_NOTIFY_WEBHOOK_URL", "https://example.com/hook")
	t.Setenv("REPAVE_OPERATOR_NOTIFY_EVENTS", "")

	cfg := LoadConfig()
	if !cfg.Enabled {
		t.Fatal("expected enabled")
	}
	if _, ok := cfg.Events[EventDriftDetected]; !ok {
		t.Fatalf("missing %s", EventDriftDetected)
	}
}

func TestSendPostsGenericWebhook(t *testing.T) {
	var received []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		received = body
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	cfg := Config{
		Enabled: true,
		URLs:    []string{srv.URL},
		Events:  map[string]struct{}{EventDriftDetected: {}},
	}
	Send(context.Background(), cfg, EventDriftDetected, Payload{
		Namespace:  "default",
		Name:       "payments",
		Repository: "/data/module",
		Message:    "pins differ",
	})

	if len(received) == 0 {
		t.Fatal("expected webhook body")
	}
}

func TestSendSkipsWhenEventDisabled(t *testing.T) {
	called := false
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
	}))
	defer srv.Close()

	cfg := Config{
		Enabled: true,
		URLs:    []string{srv.URL},
		Events:  map[string]struct{}{EventRemediationPROpened: {}},
	}
	Send(context.Background(), cfg, EventDriftDetected, Payload{Name: "x"})
	if called {
		t.Fatal("expected no request")
	}
}

func TestSendStopsWhenContextCanceled(t *testing.T) {
	started := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		close(started)
		time.Sleep(2 * time.Second)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	ctx, cancel := context.WithCancel(context.Background())
	cfg := Config{
		Enabled: true,
		URLs:    []string{srv.URL},
		Events:  map[string]struct{}{EventDriftDetected: {}},
	}
	done := make(chan struct{})
	go func() {
		defer close(done)
		Send(ctx, cfg, EventDriftDetected, Payload{Name: "x"})
	}()
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("webhook was not hit")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Fatal("Send ignored canceled context")
	}
}
