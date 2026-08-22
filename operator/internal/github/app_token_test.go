package github_test

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/opsdevcode/repave/operator/internal/github"
)

func testPrivateKeyPEM(t *testing.T) string {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	block := &pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)}
	return string(pem.EncodeToMemory(block))
}

func TestResolveAccessToken_prefersPAT(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "ghp_pat")
	t.Setenv("GITHUB_APP_ID", "1")
	t.Setenv("GITHUB_APP_INSTALLATION_ID", "2")
	t.Setenv("GITHUB_APP_PRIVATE_KEY", testPrivateKeyPEM(t))

	token, err := github.ResolveAccessToken(context.Background(), "")
	if err != nil {
		t.Fatalf("ResolveAccessToken: %v", err)
	}
	if token != "ghp_pat" {
		t.Fatalf("expected PAT, got %q", token)
	}
}

func TestResolveAccessToken_mintsInstallationToken(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, "/access_tokens") {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]string{
			"token":      "ghs_installation",
			"expires_at": time.Now().Add(time.Hour).UTC().Format(time.RFC3339),
		})
	}))
	defer server.Close()

	origTransport := http.DefaultTransport
	http.DefaultTransport = roundTripperFunc(func(req *http.Request) (*http.Response, error) {
		req.URL.Scheme = "http"
		req.URL.Host = strings.TrimPrefix(server.URL, "http://")
		return origTransport.RoundTrip(req)
	})
	defer func() { http.DefaultTransport = origTransport }()

	t.Setenv("GITHUB_APP_ID", "42")
	t.Setenv("GITHUB_APP_INSTALLATION_ID", "99")
	t.Setenv("GITHUB_APP_PRIVATE_KEY", testPrivateKeyPEM(t))

	token, err := github.ResolveAccessToken(context.Background(), "")
	if err != nil {
		t.Fatalf("ResolveAccessToken: %v", err)
	}
	if token != "ghs_installation" {
		t.Fatalf("expected installation token, got %q", token)
	}
}

func TestCredentialsConfigured(t *testing.T) {
	t.Setenv("GITHUB_TOKEN", "")
	t.Setenv("GITHUB_APP_ID", "")
	if github.CredentialsConfigured() {
		t.Fatal("expected false without credentials")
	}
	t.Setenv("GITHUB_TOKEN", "ghp_pat")
	if !github.CredentialsConfigured() {
		t.Fatal("expected true with PAT")
	}
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (f roundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}
