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
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	repavev1alpha1 "github.com/opsdevcode/repave/operator/api/v1alpha1"
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
		}
	})

	AfterEach(func() {
		repo := &repavev1alpha1.GoldenPathRepo{}
		err := k8sClient.Get(ctx, typeNamespacedName, repo)
		if err != nil {
			return
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
