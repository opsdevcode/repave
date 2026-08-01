package github

import (
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	defaultInstallationID = "default"
	defaultMinRemaining   = 50
	maxBackoffSeconds     = 300.0
)

// RateLimitSnapshot captures GitHub REST quota from response headers.
type RateLimitSnapshot struct {
	Remaining int
	Limit     int
	ResetAt   time.Time
}

// Exhausted reports whether the REST quota is depleted.
func (s RateLimitSnapshot) Exhausted() bool {
	return s.Remaining <= 0
}

// Low reports whether remaining calls are below the proactive threshold.
func (s RateLimitSnapshot) Low(minRemaining int) bool {
	return s.Remaining < minRemaining
}

// RateLimitTracker stores per-installation GitHub REST quota (thread-safe).
type RateLimitTracker struct {
	mu        sync.Mutex
	snapshots map[string]RateLimitSnapshot
}

// NewRateLimitTracker returns an empty tracker.
func NewRateLimitTracker() *RateLimitTracker {
	return &RateLimitTracker{snapshots: map[string]RateLimitSnapshot{}}
}

var defaultRateLimitTracker = NewRateLimitTracker()

// DefaultRateLimitTracker is the process-wide tracker used by remediation and campaigns.
func DefaultRateLimitTracker() *RateLimitTracker {
	return defaultRateLimitTracker
}

// ResetRateLimitTracker clears tracker state (tests only).
func ResetRateLimitTracker() {
	defaultRateLimitTracker = NewRateLimitTracker()
}

// UpdateFromHeaders records X-RateLimit-* headers when present.
func (t *RateLimitTracker) UpdateFromHeaders(headers http.Header, installationID string) {
	if headers == nil {
		return
	}
	remainingRaw := headerValue(headers, "X-RateLimit-Remaining")
	resetRaw := headerValue(headers, "X-RateLimit-Reset")
	if remainingRaw == "" || resetRaw == "" {
		return
	}
	remaining, err := strconv.Atoi(remainingRaw)
	if err != nil {
		return
	}
	limit := 5000
	if limitRaw := headerValue(headers, "X-RateLimit-Limit"); limitRaw != "" {
		if parsed, parseErr := strconv.Atoi(limitRaw); parseErr == nil {
			limit = parsed
		}
	}
	resetUnix, err := strconv.ParseInt(resetRaw, 10, 64)
	if err != nil {
		return
	}
	key := normalizeInstallationID(installationID)
	t.mu.Lock()
	defer t.mu.Unlock()
	t.snapshots[key] = RateLimitSnapshot{
		Remaining: remaining,
		Limit:     limit,
		ResetAt:   time.Unix(resetUnix, 0),
	}
}

// Snapshot returns the latest quota for an installation, if known.
func (t *RateLimitTracker) Snapshot(installationID string) (RateLimitSnapshot, bool) {
	key := normalizeInstallationID(installationID)
	t.mu.Lock()
	defer t.mu.Unlock()
	state, ok := t.snapshots[key]
	return state, ok
}

// ShouldBackoff reports whether callers should defer GitHub REST work.
func (t *RateLimitTracker) ShouldBackoff(installationID string, minRemaining int) (bool, time.Duration) {
	state, ok := t.Snapshot(installationID)
	if !ok || (!state.Exhausted() && !state.Low(minRemaining)) {
		return false, 0
	}
	delay := time.Until(state.ResetAt) + time.Second
	if delay < 0 {
		delay = 0
	}
	if delay > maxBackoffSeconds*time.Second {
		delay = maxBackoffSeconds * time.Second
	}
	return true, delay
}

// WaitIfNeeded sleeps until quota recovers when remaining is below the threshold.
func (t *RateLimitTracker) WaitIfNeeded(installationID string, minRemaining int) {
	if blocked, delay := t.ShouldBackoff(installationID, minRemaining); blocked && delay > 0 {
		time.Sleep(delay)
	}
}

// RateLimitGate reports whether remediation should defer opening a PR.
func RateLimitGate() (blocked bool, message string) {
	installationID := CurrentInstallationID()
	minRemaining := MinRemainingFromEnv()
	state, ok := DefaultRateLimitTracker().Snapshot(installationID)
	if !ok {
		return false, ""
	}
	if !state.Exhausted() && !state.Low(minRemaining) {
		return false, ""
	}
	resetIn := time.Until(state.ResetAt)
	if resetIn < 0 {
		resetIn = 0
	}
	return true, formatRateLimitMessage(state.Remaining, resetIn)
}

// CurrentInstallationID returns the configured GitHub App installation id or a stable default.
func CurrentInstallationID() string {
	cfg, err := LoadAppConfig()
	if err != nil || cfg == nil || strings.TrimSpace(cfg.InstallationID) == "" {
		return defaultInstallationID
	}
	return strings.TrimSpace(cfg.InstallationID)
}

// MinRemainingFromEnv reads REPAVE_GITHUB_RATE_LIMIT_MIN_REMAINING (default 50).
func MinRemainingFromEnv() int {
	raw := strings.TrimSpace(os.Getenv("REPAVE_GITHUB_RATE_LIMIT_MIN_REMAINING"))
	if raw == "" {
		return defaultMinRemaining
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value < 0 {
		return defaultMinRemaining
	}
	return value
}

// BackoffSeconds computes retry delay for HTTP 429 responses.
func BackoffSeconds(retryAfter string, attempt int) time.Duration {
	if retryAfter != "" {
		if seconds, err := strconv.ParseFloat(retryAfter, 64); err == nil {
			return clampBackoff(time.Duration(seconds * float64(time.Second)))
		}
	}
	delay := time.Duration(1<<attempt) * time.Second
	return clampBackoff(delay)
}

func clampBackoff(delay time.Duration) time.Duration {
	max := time.Duration(maxBackoffSeconds * float64(time.Second))
	if delay > max {
		return max
	}
	if delay < 0 {
		return 0
	}
	return delay
}

func formatRateLimitMessage(remaining int, resetIn time.Duration) string {
	seconds := int(resetIn.Seconds())
	if seconds < 0 {
		seconds = 0
	}
	return "GitHub REST rate limit low (" + strconv.Itoa(remaining) +
		" remaining); retry after quota resets in " + strconv.Itoa(seconds) + "s"
}

func headerValue(headers http.Header, name string) string {
	return strings.TrimSpace(headers.Get(name))
}

func normalizeInstallationID(installationID string) string {
	installationID = strings.TrimSpace(installationID)
	if installationID == "" {
		return defaultInstallationID
	}
	return installationID
}
