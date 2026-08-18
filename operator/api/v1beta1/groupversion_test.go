package v1beta1

import (
	"testing"

	"k8s.io/apimachinery/pkg/runtime"
)

func TestAddToSchemeRegistersHubTypes(t *testing.T) {
	scheme := runtime.NewScheme()
	if err := AddToScheme(scheme); err != nil {
		t.Fatalf("AddToScheme: %v", err)
	}
	for _, kind := range []string{"Blueprint", "GoldenPathRepo", "UpgradeCampaign"} {
		if !scheme.Recognizes(GroupVersion.WithKind(kind)) {
			t.Fatalf("scheme missing %s", kind)
		}
	}
}
