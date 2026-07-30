package v1alpha1

import (
	"fmt"

	"sigs.k8s.io/controller-runtime/pkg/conversion"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

// ConvertTo converts this Blueprint (v1alpha1) to the hub version (v1beta1).
func (src *Blueprint) ConvertTo(dst conversion.Hub) error {
	hub, ok := dst.(*repavev1beta1.Blueprint)
	if !ok {
		return fmt.Errorf("expected *v1beta1.Blueprint hub, got %T", dst)
	}
	return convertBlueprintToHub(src, hub)
}

// ConvertFrom converts the hub version (v1beta1) into this Blueprint (v1alpha1).
func (dst *Blueprint) ConvertFrom(src conversion.Hub) error {
	hub, ok := src.(*repavev1beta1.Blueprint)
	if !ok {
		return fmt.Errorf("expected *v1beta1.Blueprint hub, got %T", src)
	}
	return convertBlueprintFromHub(hub, dst)
}

func convertBlueprintToHub(src *Blueprint, dst *repavev1beta1.Blueprint) error {
	dst.ObjectMeta = src.ObjectMeta
	dst.Spec = repavev1beta1.BlueprintSpec{
		Version: src.Spec.Version,
		Standard: repavev1beta1.BlueprintStandardPins{
			Source:  src.Spec.Standard.Source,
			Version: src.Spec.Standard.Version,
		},
	}
	dst.Status = repavev1beta1.BlueprintStatus{
		ObservedGeneration: src.Status.ObservedGeneration,
	}
	return nil
}

func convertBlueprintFromHub(src *repavev1beta1.Blueprint, dst *Blueprint) error {
	dst.ObjectMeta = src.ObjectMeta
	dst.Spec = BlueprintSpec{
		Version: src.Spec.Version,
		Standard: BlueprintStandardPins{
			Source:  src.Spec.Standard.Source,
			Version: src.Spec.Standard.Version,
		},
	}
	dst.Status = BlueprintStatus{
		ObservedGeneration: src.Status.ObservedGeneration,
	}
	return nil
}
