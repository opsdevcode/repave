package controller

import (
	"context"
	"path/filepath"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
	"github.com/opsdevcode/repave/operator/internal/repave"
	"github.com/opsdevcode/repave/operator/internal/remediation"
	"github.com/opsdevcode/repave/operator/internal/status"
)

func fixtureModulePath() string {
	path, err := filepath.Abs(filepath.Join("..", "..", "testdata", "modules", "terraform-minimal"))
	Expect(err).NotTo(HaveOccurred())
	return path
}

var _ = Describe("GoldenPathRepo reconciler", func() {
	const name = "reconcile-gpr"

	ctx := context.Background()
	typeNamespacedName := types.NamespacedName{Name: name, Namespace: "default"}

	var reconciler *GoldenPathRepoReconciler

	BeforeEach(func() {
		reconciler = &GoldenPathRepoReconciler{
			Client: k8sClient,
			Scheme: scheme.Scheme,
			PlanUpgrader: &repave.StaticPlanUpgrader{
				Result: repave.PlanResult{
					BlueprintName:    "terraform-module-generic",
					BlueprintVersion: "0.8.0",
					ChangedFileCount:   5,
					Added:              []string{"README.md", "main.tf"},
					Modified:           []string{"repave.yaml"},
					Summary:            "5 file(s) differ (2 added, 1 modified, 0 removed)",
				},
			},
			RepaveConfig: repave.Config{RepoRoot: "/tmp/repave", Command: "repave"},
			ApplyUpgrader: &repave.StaticApplyUpgrader{
				Result: repave.ApplyResult{
					BlueprintName:    "terraform-module-generic",
					BlueprintVersion: "0.8.0",
					ChangedFileCount: 5,
					GitBranch:        "repave/upgrade/terraform-module-generic-9.9.9",
					CommitSHA:        "abc123",
					Summary:          "planned upgrade",
				},
			},
		}
	})

	AfterEach(func() {
		repo := &repavev1alpha1.GoldenPathRepo{}
		err := k8sClient.Get(ctx, typeNamespacedName, repo)
		if err != nil {
			return
		}
		if len(repo.Finalizers) > 0 {
			repo.Finalizers = nil
			Expect(k8sClient.Update(ctx, repo)).To(Succeed())
		}
		Expect(k8sClient.Delete(ctx, repo)).To(Succeed())
	})

	It("sets Ready when observed pins match desired", func() {
		repo := &repavev1alpha1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "default"},
			Spec: repavev1alpha1.GoldenPathRepoSpec{
				LocalPath: fixtureModulePath(),
				DesiredPins: repavev1alpha1.DesiredPins{
					BlueprintName:    "terraform-module-generic",
					BlueprintVersion: "0.1.0",
					StandardSource:   "examples/standards",
					StandardVersion:  "0.4.0",
				},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())

		_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())

		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		Expect(repo.Status.Phase).To(Equal(repavev1alpha1.GoldenPathRepoPhaseReady))
		Expect(repo.Status.ObservedPins.BlueprintVersion).To(Equal("0.1.0"))
		Expect(meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionReady)).To(BeTrue())
		Expect(meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionDriftDetected)).To(BeFalse())
		Expect(repo.Status.UpgradePlan).To(BeNil())
	})

	It("sets OutOfDate when desired pins differ from repave.yaml", func() {
		repo := &repavev1alpha1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "default"},
			Spec: repavev1alpha1.GoldenPathRepoSpec{
				LocalPath: fixtureModulePath(),
				DesiredPins: repavev1alpha1.DesiredPins{
					BlueprintName:    "terraform-module-generic",
					BlueprintVersion: "9.9.9",
					StandardSource:   "examples/standards",
					StandardVersion:  "0.4.0",
				},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())

		_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())

		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		Expect(repo.Status.Phase).To(Equal(repavev1alpha1.GoldenPathRepoPhaseOutOfDate))
		Expect(meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionDriftDetected)).To(BeTrue())
		Expect(meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionUpgradePlanned)).To(BeTrue())
		Expect(repo.Status.UpgradePlan).NotTo(BeNil())
		Expect(repo.Status.UpgradePlan.ChangedFileCount).To(Equal(5))
		Expect(repo.Status.UpgradePlan.Added).To(ContainElements("README.md", "main.tf"))
	})

	It("opens dry-run remediation when enabled and pins drift", func() {
		repo := &repavev1alpha1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "default"},
			Spec: repavev1alpha1.GoldenPathRepoSpec{
				LocalPath: fixtureModulePath(),
				DesiredPins: repavev1alpha1.DesiredPins{
					BlueprintName:    "terraform-module-generic",
					BlueprintVersion: "9.9.9",
					StandardSource:   "examples/standards",
					StandardVersion:  "0.4.0",
				},
				Remediation: repavev1alpha1.RemediationSpec{
					Enabled: true,
					DryRun:  true,
				},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())

		_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())
		_, err = reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())

		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		Expect(repo.Status.RemediationPR).NotTo(BeNil())
		Expect(repo.Status.RemediationPR.State).To(Equal(remediation.PRStatePlanned))
		Expect(meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionRemediationPR)).To(BeTrue())
	})

	It("sets OutOfDate when Blueprint catalog pins bump via blueprintRef", func() {
		bpName := "terraform-module-generic"
		bp := &repavev1alpha1.Blueprint{
			ObjectMeta: metav1.ObjectMeta{Name: bpName, Namespace: "default"},
			Spec: repavev1alpha1.BlueprintSpec{
				Version: "0.1.0",
				Standard: repavev1alpha1.BlueprintStandardPins{
					Source:  "examples/standards",
					Version: "0.4.0",
				},
			},
		}
		Expect(k8sClient.Create(ctx, bp)).To(Succeed())
		defer func() {
			_ = k8sClient.Delete(ctx, bp)
		}()

		repo := &repavev1alpha1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "default"},
			Spec: repavev1alpha1.GoldenPathRepoSpec{
				LocalPath: fixtureModulePath(),
				BlueprintRef: &repavev1alpha1.BlueprintRef{Name: bpName},
				DesiredPins: repavev1alpha1.DesiredPins{
					BlueprintName:    bpName,
					BlueprintVersion: "unused",
					StandardSource:   "unused",
					StandardVersion:  "unused",
				},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())

		_, err := reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())
		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		Expect(repo.Status.Phase).To(Equal(repavev1alpha1.GoldenPathRepoPhaseReady))

		Expect(k8sClient.Get(ctx, client.ObjectKeyFromObject(bp), bp)).To(Succeed())
		bp.Spec.Version = "9.9.9"
		Expect(k8sClient.Update(ctx, bp)).To(Succeed())

		requests := reconciler.enqueueGoldenPathReposForBlueprint(ctx, bp)
		Expect(requests).To(ContainElement(reconcile.Request{NamespacedName: typeNamespacedName}))

		_, err = reconciler.Reconcile(ctx, reconcile.Request{NamespacedName: typeNamespacedName})
		Expect(err).NotTo(HaveOccurred())
		Expect(k8sClient.Get(ctx, typeNamespacedName, repo)).To(Succeed())
		Expect(repo.Status.Phase).To(Equal(repavev1alpha1.GoldenPathRepoPhaseOutOfDate))
		Expect(meta.IsStatusConditionTrue(repo.Status.Conditions, status.ConditionDriftDetected)).To(BeTrue())
	})

	It("rejects spec with neither repoURL nor localPath at admission", func() {
		repo := &repavev1alpha1.GoldenPathRepo{
			ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: "default"},
			Spec: repavev1alpha1.GoldenPathRepoSpec{
				LocalPath: fixtureModulePath(),
				DesiredPins: repavev1alpha1.DesiredPins{
					BlueprintName:    "terraform-module-generic",
					BlueprintVersion: "0.1.0",
					StandardSource:   "examples/standards",
					StandardVersion:  "0.4.0",
				},
			},
		}
		Expect(k8sClient.Create(ctx, repo)).To(Succeed())

		repo.Spec.LocalPath = ""
		Expect(k8sClient.Update(ctx, repo)).NotTo(Succeed())
	})
})
