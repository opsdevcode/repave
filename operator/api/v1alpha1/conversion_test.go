package v1alpha1

import (
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

func TestGoldenPathRepoConvertRoundTrip(t *testing.T) {
	alpha := &GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{Name: "demo", Namespace: "default"},
		Spec: GoldenPathRepoSpec{
			LocalPath: "/modules/demo",
			DesiredPins: DesiredPins{
				BlueprintName:    "terraform-module-generic",
				BlueprintVersion: "1.0.0",
				StandardSource:   "standards/terraform-standards",
				StandardVersion:  "1.1.0",
			},
			BlueprintRef: &BlueprintRef{Name: "terraform-module-generic"},
			Remediation: RemediationSpec{
				Enabled:       true,
				DryRun:        true,
				PreserveLocal: true,
			},
		},
		Status: GoldenPathRepoStatus{
			Phase: GoldenPathRepoPhaseOutOfDate,
			ObservedPins: ObservedPins{
				BlueprintName:    "terraform-module-generic",
				BlueprintVersion: "0.9.0",
			},
			UpgradePlan: &UpgradePlan{ChangedFileCount: 3, Summary: "3 files differ"},
		},
	}

	hub := &repavev1beta1.GoldenPathRepo{}
	if err := alpha.ConvertTo(hub); err != nil {
		t.Fatalf("ConvertTo: %v", err)
	}
	if hub.Spec.LocalPath != alpha.Spec.LocalPath {
		t.Fatalf("spec.localPath = %q, want %q", hub.Spec.LocalPath, alpha.Spec.LocalPath)
	}
	if hub.Status.UpgradePlan == nil || hub.Status.UpgradePlan.ChangedFileCount != 3 {
		t.Fatalf("upgrade plan not copied: %+v", hub.Status.UpgradePlan)
	}

	back := &GoldenPathRepo{}
	if err := back.ConvertFrom(hub); err != nil {
		t.Fatalf("ConvertFrom: %v", err)
	}
	if back.Spec.Remediation.PreserveLocal != true {
		t.Fatalf("preserveLocal not round-tripped")
	}
	if back.Status.Phase != GoldenPathRepoPhaseOutOfDate {
		t.Fatalf("phase = %q, want OutOfDate", back.Status.Phase)
	}
}

func TestBlueprintConvertRoundTrip(t *testing.T) {
	alpha := &Blueprint{
		ObjectMeta: metav1.ObjectMeta{Name: "terraform-module-generic"},
		Spec: BlueprintSpec{
			Version: "1.0.0",
			Standard: BlueprintStandardPins{
				Source:  "standards/terraform-standards",
				Version: "1.1.0",
			},
		},
		Status: BlueprintStatus{ObservedGeneration: 2},
	}

	hub := &repavev1beta1.Blueprint{}
	if err := alpha.ConvertTo(hub); err != nil {
		t.Fatalf("ConvertTo: %v", err)
	}

	back := &Blueprint{}
	if err := back.ConvertFrom(hub); err != nil {
		t.Fatalf("ConvertFrom: %v", err)
	}
	if back.Spec.Version != "1.0.0" || back.Status.ObservedGeneration != 2 {
		t.Fatalf("round trip mismatch: %+v", back)
	}
}
