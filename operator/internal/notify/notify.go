package notify

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

const (
	EventDriftDetected       = "drift_detected"
	EventRemediationPROpened   = "remediation_pr_opened"
	EventRemediationPRPlanned  = "remediation_pr_planned"
)

// Config holds webhook targets and enabled operator events (from environment).
type Config struct {
	Enabled bool
	URLs    []string
	Events  map[string]struct{}
}

// LoadConfig reads REPAVE_* webhook URLs and REPAVE_OPERATOR_NOTIFY_* settings.
func LoadConfig() Config {
	urls := uniqueNonEmpty(
		os.Getenv("REPAVE_SLACK_WEBHOOK_URL"),
		os.Getenv("REPAVE_TEAMS_WEBHOOK_URL"),
		os.Getenv("REPAVE_NOTIFY_WEBHOOK_URL"),
	)
	enabled := strings.EqualFold(os.Getenv("REPAVE_OPERATOR_NOTIFY_ENABLED"), "true")
	if !enabled && len(urls) > 0 && os.Getenv("REPAVE_OPERATOR_NOTIFY_ENABLED") == "" {
		enabled = true
	}
	if strings.EqualFold(os.Getenv("REPAVE_OPERATOR_NOTIFY_ENABLED"), "false") {
		enabled = false
	}

	events := parseEvents(os.Getenv("REPAVE_OPERATOR_NOTIFY_EVENTS"))
	if len(events) == 0 {
		events = map[string]struct{}{
			EventDriftDetected:      {},
			EventRemediationPROpened: {},
		}
	}

	return Config{
		Enabled: enabled && len(urls) > 0,
		URLs:    urls,
		Events:  events,
	}
}

func parseEvents(raw string) map[string]struct{} {
	out := map[string]struct{}{}
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part != "" {
			out[part] = struct{}{}
		}
	}
	return out
}

func uniqueNonEmpty(values ...string) []string {
	seen := map[string]struct{}{}
	var out []string
	for _, v := range values {
		v = strings.TrimSpace(v)
		if v == "" {
			continue
		}
		if _, ok := seen[v]; ok {
			continue
		}
		seen[v] = struct{}{}
		out = append(out, v)
	}
	return out
}

// Payload is the generic JSON webhook body for operator events.
type Payload struct {
	Event      string `json:"event"`
	Repository string `json:"repository"`
	Namespace  string `json:"namespace"`
	Name       string `json:"name"`
	Message    string `json:"message"`
	PRURL      string `json:"pr_url,omitempty"`
	Branch     string `json:"branch,omitempty"`
}

var httpClient = &http.Client{Timeout: 10 * time.Second}

// Send delivers a notification best-effort; errors are logged only.
func Send(cfg Config, event string, payload Payload) {
	if !cfg.Enabled {
		return
	}
	if _, ok := cfg.Events[event]; !ok {
		return
	}
	payload.Event = event
	text := formatSlackText(payload)
	for _, url := range cfg.URLs {
		post(cfg, url, payload, text)
	}
}

func formatSlackText(p Payload) string {
	lines := []string{
		"*" + p.Event + "*",
		"GoldenPathRepo: `" + p.Namespace + "/" + p.Name + "`",
		"Repository: " + p.Repository,
		p.Message,
	}
	if p.PRURL != "" {
		lines = append(lines, "PR: "+p.PRURL)
	}
	if p.Branch != "" {
		lines = append(lines, "Branch: `"+p.Branch+"`")
	}
	return strings.Join(lines, "\n")
}

func post(_ Config, url string, payload Payload, text string) {
	for attempt := 0; attempt < 3; attempt++ {
		body := encodeBody(url, payload, text)
		req, err := http.NewRequest(http.MethodPost, url, body)
		if err != nil {
			log.Printf("operator notify: build request: %v", err)
			return
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := httpClient.Do(req)
		if err == nil && resp.StatusCode < 400 {
			resp.Body.Close()
			return
		}
		if resp != nil {
			resp.Body.Close()
		}
		if attempt < 2 {
			time.Sleep(time.Duration(attempt+1) * 500 * time.Millisecond)
		}
	}
	log.Printf("operator notify: delivery failed for event %s", payload.Event)
}

func encodeBody(url string, payload Payload, text string) io.Reader {
	switch {
	case strings.Contains(url, "hooks.slack.com"):
		return bytes.NewReader(mustJSON(map[string]string{"text": text}))
	case strings.Contains(url, "webhook.office.com"):
		return bytes.NewReader(mustJSON(map[string]string{
			"@type":    "MessageCard",
			"@context": "https://schema.org/extensions",
			"summary":  "repave operator",
			"text":     text,
		}))
	default:
		return bytes.NewReader(mustJSON(payload))
	}
}

func mustJSON(v any) []byte {
	data, err := json.Marshal(v)
	if err != nil {
		return []byte("{}")
	}
	return data
}
