package v1alpha1

import (
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/conversion"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

// ConvertTo converts this GoldenPathRepo (v1alpha1) to the hub version (v1beta1).
func (src *GoldenPathRepo) ConvertTo(dst conversion.Hub) error {
	hub, ok := dst.(*repavev1beta1.GoldenPathRepo)
	if !ok {
		return fmt.Errorf("expected *v1beta1.GoldenPathRepo hub, got %T", dst)
	}
	return convertGoldenPathRepoToHub(src, hub)
}

// ConvertFrom converts the hub version (v1beta1) into this GoldenPathRepo (v1alpha1).
func (dst *GoldenPathRepo) ConvertFrom(src conversion.Hub) error {
	hub, ok := src.(*repavev1beta1.GoldenPathRepo)
	if !ok {
		return fmt.Errorf("expected *v1beta1.GoldenPathRepo hub, got %T", src)
	}
	return convertGoldenPathRepoFromHub(hub, dst)
}

func convertGoldenPathRepoToHub(src *GoldenPathRepo, dst *repavev1beta1.GoldenPathRepo) error {
	dst.ObjectMeta = src.ObjectMeta
	dst.Spec = repavev1beta1.GoldenPathRepoSpec{
		RepoURL:   src.Spec.RepoURL,
		LocalPath: src.Spec.LocalPath,
		DesiredPins: repavev1beta1.DesiredPins{
			BlueprintName:    src.Spec.DesiredPins.BlueprintName,
			BlueprintVersion: src.Spec.DesiredPins.BlueprintVersion,
			StandardSource:   src.Spec.DesiredPins.StandardSource,
			StandardVersion:  src.Spec.DesiredPins.StandardVersion,
		},
		Remediation: repavev1beta1.RemediationSpec{
			Enabled:       src.Spec.Remediation.Enabled,
			DryRun:        src.Spec.Remediation.DryRun,
			BaseBranch:    src.Spec.Remediation.BaseBranch,
			BranchPrefix:  src.Spec.Remediation.BranchPrefix,
			PreserveLocal: src.Spec.Remediation.PreserveLocal,
		},
	}
	if src.Spec.BlueprintRef != nil {
		dst.Spec.BlueprintRef = &repavev1beta1.BlueprintRef{Name: src.Spec.BlueprintRef.Name}
	}
	dst.Status = repavev1beta1.GoldenPathRepoStatus{
		Conditions:         append([]metav1.Condition(nil), src.Status.Conditions...),
		Phase:              repavev1beta1.GoldenPathRepoPhase(src.Status.Phase),
		Message:            src.Status.Message,
		ObservedGeneration: src.Status.ObservedGeneration,
		ObservedPins: repavev1beta1.ObservedPins{
			BlueprintName:    src.Status.ObservedPins.BlueprintName,
			BlueprintVersion: src.Status.ObservedPins.BlueprintVersion,
			StandardSource:   src.Status.ObservedPins.StandardSource,
			StandardVersion:  src.Status.ObservedPins.StandardVersion,
		},
	}
	if src.Status.UpgradePlan != nil {
		dst.Status.UpgradePlan = &repavev1beta1.UpgradePlan{
			ChangedFileCount: src.Status.UpgradePlan.ChangedFileCount,
			BlueprintName:    src.Status.UpgradePlan.BlueprintName,
			BlueprintVersion: src.Status.UpgradePlan.BlueprintVersion,
			Added:            append([]string(nil), src.Status.UpgradePlan.Added...),
			Modified:         append([]string(nil), src.Status.UpgradePlan.Modified...),
			Removed:          append([]string(nil), src.Status.UpgradePlan.Removed...),
			Summary:          src.Status.UpgradePlan.Summary,
		}
	}
	if src.Status.RemediationPR != nil {
		dst.Status.RemediationPR = &repavev1beta1.RemediationPRStatus{
			URL:                     src.Status.RemediationPR.URL,
			Number:                  src.Status.RemediationPR.Number,
			Branch:                  src.Status.RemediationPR.Branch,
			Title:                   src.Status.RemediationPR.Title,
			State:                   src.Status.RemediationPR.State,
			DesiredBlueprintVersion: src.Status.RemediationPR.DesiredBlueprintVersion,
		}
	}
	return nil
}

func convertGoldenPathRepoFromHub(src *repavev1beta1.GoldenPathRepo, dst *GoldenPathRepo) error {
	dst.ObjectMeta = src.ObjectMeta
	dst.Spec = GoldenPathRepoSpec{
		RepoURL:   src.Spec.RepoURL,
		LocalPath: src.Spec.LocalPath,
		DesiredPins: DesiredPins{
			BlueprintName:    src.Spec.DesiredPins.BlueprintName,
			BlueprintVersion: src.Spec.DesiredPins.BlueprintVersion,
			StandardSource:   src.Spec.DesiredPins.StandardSource,
			StandardVersion:  src.Spec.DesiredPins.StandardVersion,
		},
		Remediation: RemediationSpec{
			Enabled:       src.Spec.Remediation.Enabled,
			DryRun:        src.Spec.Remediation.DryRun,
			BaseBranch:    src.Spec.Remediation.BaseBranch,
			BranchPrefix:  src.Spec.Remediation.BranchPrefix,
			PreserveLocal: src.Spec.Remediation.PreserveLocal,
		},
	}
	if src.Spec.BlueprintRef != nil {
		dst.Spec.BlueprintRef = &BlueprintRef{Name: src.Spec.BlueprintRef.Name}
	}
	dst.Status = GoldenPathRepoStatus{
		Conditions:         append([]metav1.Condition(nil), src.Status.Conditions...),
		Phase:              GoldenPathRepoPhase(src.Status.Phase),
		Message:            src.Status.Message,
		ObservedGeneration: src.Status.ObservedGeneration,
		ObservedPins: ObservedPins{
			BlueprintName:    src.Status.ObservedPins.BlueprintName,
			BlueprintVersion: src.Status.ObservedPins.BlueprintVersion,
			StandardSource:   src.Status.ObservedPins.StandardSource,
			StandardVersion:  src.Status.ObservedPins.StandardVersion,
		},
	}
	if src.Status.UpgradePlan != nil {
		dst.Status.UpgradePlan = &UpgradePlan{
			ChangedFileCount: src.Status.UpgradePlan.ChangedFileCount,
			BlueprintName:    src.Status.UpgradePlan.BlueprintName,
			BlueprintVersion: src.Status.UpgradePlan.BlueprintVersion,
			Added:            append([]string(nil), src.Status.UpgradePlan.Added...),
			Modified:         append([]string(nil), src.Status.UpgradePlan.Modified...),
			Removed:          append([]string(nil), src.Status.UpgradePlan.Removed...),
			Summary:          src.Status.UpgradePlan.Summary,
		}
	}
	if src.Status.RemediationPR != nil {
		dst.Status.RemediationPR = &RemediationPRStatus{
			URL:                     src.Status.RemediationPR.URL,
			Number:                  src.Status.RemediationPR.Number,
			Branch:                  src.Status.RemediationPR.Branch,
			Title:                   src.Status.RemediationPR.Title,
			State:                   src.Status.RemediationPR.State,
			DesiredBlueprintVersion: src.Status.RemediationPR.DesiredBlueprintVersion,
		}
	}
	return nil
}
