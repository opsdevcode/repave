package github

import (
	"context"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const (
	tokenRefreshBuffer  = 5 * time.Minute
	appJWTLifetime      = 9 * time.Minute
	appTokenHTTPTimeout = 30 * time.Second
)

var appTokenHTTPClient = &http.Client{Timeout: appTokenHTTPTimeout}

// AppConfig holds GitHub App credentials from the environment.
type AppConfig struct {
	AppID          string
	InstallationID string
	PrivateKeyPEM  string
}

// LoadAppConfig reads GitHub App credentials from the environment.
func LoadAppConfig() (*AppConfig, error) {
	appID := strings.TrimSpace(os.Getenv("GITHUB_APP_ID"))
	installationID := strings.TrimSpace(os.Getenv("GITHUB_APP_INSTALLATION_ID"))
	privateKey := strings.TrimSpace(os.Getenv("GITHUB_APP_PRIVATE_KEY"))
	if privateKey == "" {
		keyFile := strings.TrimSpace(os.Getenv("GITHUB_APP_PRIVATE_KEY_FILE"))
		if keyFile != "" {
			raw, err := os.ReadFile(keyFile)
			if err != nil {
				return nil, fmt.Errorf("read GITHUB_APP_PRIVATE_KEY_FILE: %w", err)
			}
			privateKey = strings.TrimSpace(string(raw))
		}
	}
	privateKey = strings.ReplaceAll(privateKey, `\n`, "\n")
	if appID == "" || installationID == "" || privateKey == "" {
		return nil, nil
	}
	return &AppConfig{
		AppID:          appID,
		InstallationID: installationID,
		PrivateKeyPEM:  privateKey,
	}, nil
}

// CredentialsConfigured reports whether PAT or App credentials are present.
func CredentialsConfigured() bool {
	if strings.TrimSpace(os.Getenv("GITHUB_TOKEN")) != "" {
		return true
	}
	cfg, err := LoadAppConfig()
	return err == nil && cfg != nil
}

type installationTokenCache struct {
	mu        sync.Mutex
	token     string
	expiresAt time.Time
}

var defaultInstallationTokenCache installationTokenCache

// ResolveAccessToken returns an explicit token, PAT, or a cached installation token.
func ResolveAccessToken(ctx context.Context, explicit string) (string, error) {
	if strings.TrimSpace(explicit) != "" {
		return strings.TrimSpace(explicit), nil
	}
	if pat := strings.TrimSpace(os.Getenv("GITHUB_TOKEN")); pat != "" {
		return pat, nil
	}
	cfg, err := LoadAppConfig()
	if err != nil {
		return "", err
	}
	if cfg == nil {
		return "", nil
	}
	return defaultInstallationTokenCache.get(ctx, cfg)
}

func (c *installationTokenCache) get(ctx context.Context, cfg *AppConfig) (string, error) {
	c.mu.Lock()
	now := time.Now()
	if c.token != "" && now.Before(c.expiresAt.Add(-tokenRefreshBuffer)) {
		token := c.token
		c.mu.Unlock()
		return token, nil
	}
	c.mu.Unlock()
	token, expiresAt, err := fetchInstallationToken(ctx, cfg)
	if err != nil {
		return "", err
	}
	c.mu.Lock()
	c.token = token
	c.expiresAt = expiresAt
	c.mu.Unlock()
	return token, nil
}

func mintAppJWT(cfg *AppConfig) (string, error) {
	block, _ := pem.Decode([]byte(cfg.PrivateKeyPEM))
	if block == nil {
		return "", fmt.Errorf("invalid GitHub App private key PEM")
	}
	key, err := x509.ParsePKCS1PrivateKey(block.Bytes)
	if err != nil {
		parsed, parseErr := x509.ParsePKCS8PrivateKey(block.Bytes)
		if parseErr != nil {
			return "", fmt.Errorf("parse GitHub App private key: %w", err)
		}
		var ok bool
		key, ok = parsed.(*rsa.PrivateKey)
		if !ok {
			return "", fmt.Errorf("GitHub App private key must be RSA")
		}
	}
	now := time.Now()
	claims := jwt.MapClaims{
		"iat": now.Add(-time.Minute).Unix(),
		"exp": now.Add(appJWTLifetime).Unix(),
		"iss": cfg.AppID,
	}
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	return token.SignedString(key)
}

type accessTokenResponse struct {
	Token     string `json:"token"`
	ExpiresAt string `json:"expires_at"`
}

func fetchInstallationToken(ctx context.Context, cfg *AppConfig) (string, time.Time, error) {
	appJWT, err := mintAppJWT(cfg)
	if err != nil {
		return "", time.Time{}, err
	}
	url := fmt.Sprintf(
		"https://api.github.com/app/installations/%s/access_tokens",
		cfg.InstallationID,
	)
	reqCtx, cancel := context.WithTimeout(ctx, appTokenHTTPTimeout)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodPost, url, nil)
	if err != nil {
		return "", time.Time{}, err
	}
	req.Header.Set("Authorization", "Bearer "+appJWT)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")

	resp, err := appTokenHTTPClient.Do(req)
	if err != nil {
		return "", time.Time{}, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", time.Time{}, fmt.Errorf("read GitHub installation token response: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", time.Time{}, fmt.Errorf("GitHub API %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	DefaultRateLimitTracker().UpdateFromHeaders(resp.Header, cfg.InstallationID)
	var parsed accessTokenResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return "", time.Time{}, err
	}
	token := strings.TrimSpace(parsed.Token)
	if token == "" {
		return "", time.Time{}, fmt.Errorf("GitHub installation token response missing token")
	}
	expiresAt, err := time.Parse(time.RFC3339, strings.TrimSpace(parsed.ExpiresAt))
	if err != nil {
		expiresAt = time.Now().Add(time.Hour)
	}
	return token, expiresAt, nil
}

// ParseInstallationID validates installation id when needed in tests.
func ParseInstallationID(raw string) (int64, error) {
	return strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
}
