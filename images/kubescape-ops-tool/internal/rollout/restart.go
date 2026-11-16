package rollout

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
)

const RestartedAtAnnotation = "kubectl.kubernetes.io/restartedAt"

type Options struct {
	Namespace  string
	Deployment string
}

const usage = `Usage: kubescape-ops-tool rollout-restart [flags]
      --namespace   Namespace of the deployment (required)
      --deployment  Name of the deployment to restart (required)
`

func ParseFlags(args []string, errOut io.Writer) (Options, error) {
	var o Options
	fs := flag.NewFlagSet("rollout-restart", flag.ContinueOnError)
	fs.SetOutput(errOut)
	fs.Usage = func() { fmt.Fprint(errOut, usage) }
	fs.StringVar(&o.Namespace, "namespace", "", "Namespace of the deployment (required)")
	fs.StringVar(&o.Namespace, "n", "", "Namespace of the deployment (required)")
	fs.StringVar(&o.Deployment, "deployment", "", "Name of the deployment to restart (required)")
	fs.StringVar(&o.Deployment, "d", "", "Name of the deployment to restart (required)")
	if err := fs.Parse(args); err != nil {
		return o, err
	}
	if o.Namespace == "" || o.Deployment == "" {
		fmt.Fprint(errOut, usage)
		return o, fmt.Errorf("--namespace and --deployment required")
	}
	return o, nil
}

// Restart applies the same pod-template annotation patch as `kubectl rollout restart`.
func Restart(ctx context.Context, kc kubernetes.Interface, o Options, now time.Time) error {
	body, err := json.Marshal(map[string]any{
		"spec": map[string]any{
			"template": map[string]any{
				"metadata": map[string]any{
					"annotations": map[string]any{
						RestartedAtAnnotation: now.Format(time.RFC3339),
					},
				},
			},
		},
	})
	if err != nil {
		return err
	}
	if _, err := kc.AppsV1().Deployments(o.Namespace).Patch(ctx, o.Deployment, types.StrategicMergePatchType, body, metav1.PatchOptions{}); err != nil {
		return fmt.Errorf("restart deployment %s/%s: %w", o.Namespace, o.Deployment, err)
	}
	slog.Info("restarted deployment", "namespace", o.Namespace, "deployment", o.Deployment)
	return nil
}
