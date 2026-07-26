package notify

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
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
	Send(cfg, EventDriftDetected, Payload{
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
	Send(cfg, EventDriftDetected, Payload{Name: "x"})
	if called {
		t.Fatal("expected no request")
	}
}
