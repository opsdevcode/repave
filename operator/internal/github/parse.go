package github

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"
)

var githubHTTPS = regexp.MustCompile(`^https://github\.com/([^/]+)/([^/.]+)(?:\.git)?/?$`)
var githubSSH = regexp.MustCompile(`^git@github\.com:([^/]+)/([^/.]+)(?:\.git)?$`)

// Repository identifies a GitHub owner/name pair.
type Repository struct {
	Owner string
	Name  string
}

// ParseRepositoryURL accepts https or git@github.com remote URLs.
func ParseRepositoryURL(raw string) (Repository, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return Repository{}, fmt.Errorf("empty repository URL")
	}

	if matches := githubHTTPS.FindStringSubmatch(trimmed); len(matches) == 3 {
		return Repository{Owner: matches[1], Name: matches[2]}, nil
	}
	if matches := githubSSH.FindStringSubmatch(trimmed); len(matches) == 3 {
		return Repository{Owner: matches[1], Name: matches[2]}, nil
	}

	parsed, err := url.Parse(trimmed)
	if err == nil && strings.EqualFold(parsed.Host, "github.com") {
		parts := strings.Split(strings.Trim(parsed.Path, "/"), "/")
		if len(parts) >= 2 {
			name := strings.TrimSuffix(parts[1], ".git")
			return Repository{Owner: parts[0], Name: name}, nil
		}
	}

	return Repository{}, fmt.Errorf("unsupported GitHub repository URL: %s", raw)
}

// WebURL returns the canonical https URL for the repository.
func (r Repository) WebURL() string {
	return fmt.Sprintf("https://github.com/%s/%s", r.Owner, r.Name)
}
