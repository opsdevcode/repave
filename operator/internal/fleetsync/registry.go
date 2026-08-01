package fleetsync

import (
	"bufio"
	"encoding/json"
	"os"
	"sort"
	"strings"
)

const (
	eventRegister   = "register"
	eventUnregister = "unregister"
)

// Entry is one repository in the folded fleet registry.
type Entry struct {
	RepoURL          string
	BlueprintName    string
	BlueprintVersion string
	StandardSource   string
	StandardVersion  string
	Owner            string
}

// ReadRegistry folds JSONL register/unregister events into current fleet entries.
func ReadRegistry(path string) ([]Entry, error) {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer file.Close()

	current := map[string]Entry{}
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var payload map[string]any
		if err := json.Unmarshal([]byte(line), &payload); err != nil {
			continue
		}
		repoURL := strings.TrimSpace(stringField(payload, "repo_url"))
		if repoURL == "" {
			continue
		}
		event := strings.TrimSpace(stringField(payload, "event"))
		if event == eventUnregister {
			delete(current, repoURL)
			continue
		}
		if event != eventRegister {
			continue
		}
		entry := Entry{
			RepoURL:          repoURL,
			BlueprintName:    strings.TrimSpace(stringField(payload, "blueprint_name")),
			BlueprintVersion: strings.TrimSpace(stringField(payload, "blueprint_version")),
			StandardSource:   strings.TrimSpace(stringField(payload, "standard_source")),
			StandardVersion:  strings.TrimSpace(stringField(payload, "standard_version")),
			Owner:            strings.TrimSpace(stringField(payload, "owner")),
		}
		if entry.BlueprintName == "" {
			continue
		}
		current[repoURL] = entry
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}

	out := make([]Entry, 0, len(current))
	for _, entry := range current {
		out = append(out, entry)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].RepoURL < out[j].RepoURL
	})
	return out, nil
}

func stringField(payload map[string]any, key string) string {
	raw, ok := payload[key]
	if !ok || raw == nil {
		return ""
	}
	switch value := raw.(type) {
	case string:
		return value
	default:
		return ""
	}
}
