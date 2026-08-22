package notify

import (
	"context"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	repavev1beta1 "github.com/opsdevcode/repave/operator/api/v1beta1"
)

// SendGoldenPathRepoEvent delivers a webhook notification for a GoldenPathRepo event.
func SendGoldenPathRepoEvent(
	ctx context.Context,
	event string,
	meta metav1.ObjectMeta,
	spec repavev1beta1.GoldenPathRepoSpec,
	branch string,
	prURL string,
	message string,
) {
	repository := spec.RepoURL
	if repository == "" {
		repository = spec.LocalPath
	}
	cfg := LoadConfig()
	Send(ctx, cfg, event, Payload{
		Namespace:  meta.Namespace,
		Name:       meta.Name,
		Repository: repository,
		Message:    message,
		PRURL:      prURL,
		Branch:     branch,
	})
}
