package fleetsync

import (
	"regexp"
	"strings"
)

var nonAlnum = regexp.MustCompile(`[^a-z0-9]+`)

const maxResourceName = 200

// ResourceName derives a stable GoldenPathRepo metadata.name from a repo URL.
func ResourceName(repoURL string) string {
	stripped := strings.TrimSpace(repoURL)
	stripped = regexp.MustCompile(`(?i)^[a-z]+://`).ReplaceAllString(stripped, "")
	stripped = regexp.MustCompile(`^[^/@]+@`).ReplaceAllString(stripped, "")
	stripped = strings.ReplaceAll(stripped, ":", "/")
	stripped = strings.TrimSuffix(stripped, "/")
	if strings.HasSuffix(strings.ToLower(stripped), ".git") {
		stripped = stripped[:len(stripped)-4]
	}
	parts := []string{}
	for _, part := range strings.Split(stripped, "/") {
		if part != "" {
			parts = append(parts, part)
		}
	}
	tail := parts
	if len(parts) >= 3 {
		tail = parts[len(parts)-2:]
	} else if len(parts) >= 1 {
		tail = parts[len(parts)-1:]
	}
	slug := nonAlnum.ReplaceAllString(strings.ToLower(strings.Join(tail, "-")), "-")
	slug = strings.Trim(slug, "-")
	if slug == "" {
		slug = "fleet-repo"
	}
	if len(slug) > maxResourceName {
		slug = strings.Trim(slug[:maxResourceName], "-")
	}
	return slug
}
