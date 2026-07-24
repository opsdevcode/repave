package pins_test

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/pins"
)

func TestEffectiveDesiredStaticPins(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, repavev1alpha1.AddToScheme(scheme))

	repo := &repavev1alpha1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{Name: "mod", Namespace: "default"},
		Spec: repavev1alpha1.GoldenPathRepoSpec{
			DesiredPins: repavev1alpha1.DesiredPins{
				BlueprintName:    "terraform-module-generic",
				BlueprintVersion: "0.8.0",
				StandardSource:   "examples/standards",
				StandardVersion:  "0.4.0",
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(repo).Build()
	got, err := pins.EffectiveDesired(context.Background(), c, repo)
	require.NoError(t, err)
	require.Equal(t, "0.8.0", got.BlueprintVersion)
}

func TestEffectiveDesiredFromBlueprintRef(t *testing.T) {
	scheme := runtime.NewScheme()
	require.NoError(t, repavev1alpha1.AddToScheme(scheme))

	bp := &repavev1alpha1.Blueprint{
		ObjectMeta: metav1.ObjectMeta{Name: "terraform-module-generic", Namespace: "default"},
		Spec: repavev1alpha1.BlueprintSpec{
			Version: "0.9.0",
			Standard: repavev1alpha1.BlueprintStandardPins{
				Source:  "examples/standards",
				Version: "0.5.0",
			},
		},
	}
	repo := &repavev1alpha1.GoldenPathRepo{
		ObjectMeta: metav1.ObjectMeta{Name: "mod", Namespace: "default"},
		Spec: repavev1alpha1.GoldenPathRepoSpec{
			BlueprintRef: &repavev1alpha1.BlueprintRef{Name: "terraform-module-generic"},
			DesiredPins: repavev1alpha1.DesiredPins{
				BlueprintName:    "terraform-module-generic",
				BlueprintVersion: "ignored",
				StandardSource:   "ignored",
				StandardVersion:  "ignored",
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(bp, repo).Build()
	got, err := pins.EffectiveDesired(context.Background(), c, repo)
	require.NoError(t, err)
	require.Equal(t, "0.9.0", got.BlueprintVersion)
	require.Equal(t, "0.5.0", got.StandardVersion)
}
