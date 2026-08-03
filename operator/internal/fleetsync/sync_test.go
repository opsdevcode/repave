package fleetsync

import (
	"context"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

func TestSyncGoldenPathReposCreatesUpdatesPrunes(t *testing.T) {
	scheme := runtime.NewScheme()
	if err := repavev1beta1.AddToScheme(scheme); err != nil {
		t.Fatal(err)
	}

	orphan := &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "stale-repo",
			Namespace: "default",
			Labels:    map[string]string{managedByLabel: managedByValue},
		},
		Spec: repavev1beta1.GoldenPathRepoSpec{
			RepoURL: "https://github.com/acme/stale",
			DesiredPins: repavev1beta1.DesiredPins{
				BlueprintName:    "bp",
				BlueprintVersion: "1.0.0",
				StandardSource:   "standards/x",
				StandardVersion:  "1.0.0",
			},
		},
	}
	existing := &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "acme-live",
			Namespace: "default",
			Labels:    map[string]string{managedByLabel: managedByValue},
		},
		Spec: repavev1beta1.GoldenPathRepoSpec{
			RepoURL: "https://github.com/acme/live",
			DesiredPins: repavev1beta1.DesiredPins{
				BlueprintName:    "bp",
				BlueprintVersion: "1.0.0",
				StandardSource:   "standards/x",
				StandardVersion:  "1.0.0",
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(orphan, existing).Build()
	cfg := Config{Namespace: "default", EnableRemediation: true}
	entries := []Entry{
		{
			RepoURL:          "https://github.com/acme/live",
			BlueprintName:    "bp",
			BlueprintVersion: "2.0.0",
			StandardSource:   "standards/x",
			StandardVersion:  "2.0.0",
			Owner:            "platform",
		},
		{
			RepoURL:          "https://github.com/acme/new",
			BlueprintName:    "bp",
			BlueprintVersion: "1.0.0",
			StandardSource:   "standards/x",
			StandardVersion:  "1.0.0",
		},
	}

	created, updated, pruned, err := SyncGoldenPathRepos(context.Background(), c, cfg, entries)
	if err != nil {
		t.Fatal(err)
	}
	if created != 1 || updated != 1 || pruned != 1 {
		t.Fatalf("created=%d updated=%d pruned=%d", created, updated, pruned)
	}

	var list repavev1beta1.GoldenPathRepoList
	if err := c.List(context.Background(), &list); err != nil {
		t.Fatal(err)
	}
	if len(list.Items) != 2 {
		t.Fatalf("expected 2 GPRs, got %d", len(list.Items))
	}
	for i := range list.Items {
		gpr := list.Items[i]
		if gpr.Name == "acme-live" {
			if gpr.Spec.DesiredPins.BlueprintVersion != "2.0.0" {
				t.Fatalf("live repo not updated: %#v", gpr.Spec.DesiredPins)
			}
			if !gpr.Spec.Remediation.Enabled {
				t.Fatal("expected remediation enabled")
			}
			if gpr.Annotations["repave.dev/owner"] != "platform" {
				t.Fatalf("owner annotation = %q", gpr.Annotations["repave.dev/owner"])
			}
		}
	}
}

func TestSyncGoldenPathReposPreservesNonFleetGPR(t *testing.T) {
	scheme := runtime.NewScheme()
	if err := repavev1beta1.AddToScheme(scheme); err != nil {
		t.Fatal(err)
	}

	manual := &repavev1beta1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "manual-repo",
			Namespace: "default",
		},
		Spec: repavev1beta1.GoldenPathRepoSpec{
			RepoURL: "https://github.com/acme/manual",
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(manual).Build()
	cfg := Config{Namespace: "default"}

	created, updated, pruned, err := SyncGoldenPathRepos(context.Background(), c, cfg, nil)
	if err != nil {
		t.Fatal(err)
	}
	if created != 0 || updated != 0 || pruned != 0 {
		t.Fatalf("created=%d updated=%d pruned=%d", created, updated, pruned)
	}

	var list repavev1beta1.GoldenPathRepoList
	if err := c.List(context.Background(), &list); err != nil {
		t.Fatal(err)
	}
	if len(list.Items) != 1 || list.Items[0].Name != "manual-repo" {
		t.Fatalf("non-fleet GPR should remain: %#v", list.Items)
	}
}
