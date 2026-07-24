package pins

import (
	"context"
	"fmt"

	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/drift"
)

// EffectiveDesired resolves pins for inventory, upgrade, and remediation.
// When spec.blueprintRef is set, blueprint and standard versions come from the Blueprint CR.
func EffectiveDesired(
	ctx context.Context,
	c client.Reader,
	repo *repavev1alpha1.GoldenPathRepo,
) (drift.PinSet, error) {
	if repo.Spec.BlueprintRef == nil || repo.Spec.BlueprintRef.Name == "" {
		return drift.PinsFromDesired(repo.Spec), nil
	}

	refName := repo.Spec.BlueprintRef.Name
	var bp repavev1alpha1.Blueprint
	key := types.NamespacedName{Name: refName, Namespace: repo.Namespace}
	if err := c.Get(ctx, key, &bp); err != nil {
		if errors.IsNotFound(err) {
			return drift.PinSet{}, fmt.Errorf("blueprint %q not found in namespace %q", refName, repo.Namespace)
		}
		return drift.PinSet{}, err
	}

	blueprintName := repo.Spec.DesiredPins.BlueprintName
	if blueprintName == "" {
		blueprintName = bp.Name
	}
	if blueprintName != bp.Name {
		return drift.PinSet{}, fmt.Errorf(
			"spec.desiredPins.blueprintName %q must match blueprintRef %q",
			blueprintName,
			bp.Name,
		)
	}

	pins := drift.PinSet{
		BlueprintName:    blueprintName,
		BlueprintVersion: bp.Spec.Version,
		StandardSource:   bp.Spec.Standard.Source,
		StandardVersion:  bp.Spec.Standard.Version,
	}
	if err := pins.Validate(); err != nil {
		return drift.PinSet{}, err
	}
	return pins, nil
}
