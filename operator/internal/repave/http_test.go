package repave

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHTTPPlanUpgraderUsesRepoURL(t *testing.T) {
	var got map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != v2PlanPath {
			t.Fatalf("path = %q", r.URL.Path)
		}
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Fatal(err)
		}
		_ = json.NewEncoder(w).Encode(PlanResult{
			BlueprintName:    "terraform-module-generic",
			BlueprintVersion: "1.0.0",
			ChangedFileCount: 2,
			Summary:          "ok",
		})
	}))
	defer server.Close()

	upgrader := HTTPPlanUpgrader{BaseURL: server.URL}
	result, err := upgrader.PlanUpgrade(
		context.Background(),
		Config{},
		"https://github.com/acme/module.git",
		"terraform-module-generic",
	)
	if err != nil {
		t.Fatalf("PlanUpgrade: %v", err)
	}
	if got["repo_url"] != "https://github.com/acme/module.git" {
		t.Fatalf("repo_url = %v", got["repo_url"])
	}
	if result.ChangedFileCount != 2 {
		t.Fatalf("changed = %d", result.ChangedFileCount)
	}
}

func TestHTTPApplyUpgraderSetsPushFlag(t *testing.T) {
	var got map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != v2ApplyPath {
			t.Fatalf("path = %q", r.URL.Path)
		}
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Fatal(err)
		}
		_ = json.NewEncoder(w).Encode(ApplyResult{
			GitBranch: "repave/upgrade/test",
			CommitSHA: "abc123",
			Pushed:    true,
		})
	}))
	defer server.Close()

	applier := HTTPApplyUpgrader{BaseURL: server.URL}
	result, err := applier.ApplyUpgrade(
		context.Background(),
		Config{},
		"https://github.com/acme/module.git",
		"terraform-module-generic",
		"repave/upgrade/test",
		"upgrade",
		false,
		true,
	)
	if err != nil {
		t.Fatalf("ApplyUpgrade: %v", err)
	}
	if got["push"] != true {
		t.Fatalf("push = %v", got["push"])
	}
	if !result.Pushed {
		t.Fatal("expected pushed result")
	}
}

func TestUpgradeTargetPrefersRepoURLInHTTPMode(t *testing.T) {
	cfg := Config{APIURL: "http://api"}
	got, err := UpgradeTarget("https://github.com/acme/mod.git", "/local", "/workspace", cfg)
	if err != nil {
		t.Fatalf("UpgradeTarget: %v", err)
	}
	if got != "https://github.com/acme/mod.git" {
		t.Fatalf("got %q", got)
	}
}

func TestUpgradeTargetHTTPModeRequiresRepoURL(t *testing.T) {
	cfg := Config{APIURL: "http://api"}
	_, err := UpgradeTarget("", "/local", "/workspace", cfg)
	if err == nil {
		t.Fatal("expected error when HTTP mode has no repoURL")
	}
}

func TestUpgradeTargetCLIModeUsesLocalPath(t *testing.T) {
	got, err := UpgradeTarget("", "/local", "/workspace", Config{})
	if err != nil {
		t.Fatalf("UpgradeTarget: %v", err)
	}
	if got != "/local" {
		t.Fatalf("got %q", got)
	}
}

func TestNewPlanUpgraderSelectsHTTP(t *testing.T) {
	cfg := Config{APIURL: "http://api"}
	if _, ok := NewPlanUpgrader(cfg).(HTTPPlanUpgrader); !ok {
		t.Fatal("expected HTTPPlanUpgrader")
	}
	if _, ok := NewPlanUpgrader(Config{RepoRoot: "/repave"}).(CLIPlanUpgrader); !ok {
		t.Fatal("expected CLIPlanUpgrader")
	}
}
