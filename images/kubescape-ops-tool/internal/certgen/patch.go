package certgen

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
	aggregator "k8s.io/kube-aggregator/pkg/client/clientset_generated/clientset"
)

const (
	ResourceAPIService = "apiservice"
	ResourceVWC        = "vwc"
)

type PatchOptions struct {
	Namespace     string
	SecretName    string
	CAName        string
	ResourceType  string
	ResourceName  string
	Retries       int
	RetryInterval int
}

const patchUsage = `Usage: kubescape-ops-tool certgen-patch [flags]
  -n, --namespace        Namespace of the secret (required)
  -s, --secret-name      Name of the secret holding the CA (required)
  -c, --ca-name          Key inside the secret holding the CA cert (default: ca)
  -t, --resource-type    Resource to patch: apiservice | vwc (required)
  -r, --resource-name    Name of the resource to patch (required)
      --retries          Max patch attempts (default: 60)
      --retry-interval   Seconds between attempts (default: 5)
`

// ParsePatchFlags mirrors charts/kubescape-operator/scripts/certgen-patch.sh's flag surface.
func ParsePatchFlags(args []string, errOut io.Writer) (PatchOptions, error) {
	var o PatchOptions
	fs := flag.NewFlagSet("certgen-patch", flag.ContinueOnError)
	fs.SetOutput(errOut)
	fs.Usage = func() { fmt.Fprint(errOut, patchUsage) }

	for _, f := range []struct {
		target       *string
		short, long  string
		def, helpTxt string
	}{
		{&o.Namespace, "n", "namespace", "", "Namespace of the secret (required)"},
		{&o.SecretName, "s", "secret-name", "", "Name of the secret holding the CA (required)"},
		{&o.CAName, "c", "ca-name", "ca", "Key inside the secret holding the CA cert"},
		{&o.ResourceType, "t", "resource-type", "", "Resource to patch: apiservice | vwc (required)"},
		{&o.ResourceName, "r", "resource-name", "", "Name of the resource to patch (required)"},
	} {
		fs.StringVar(f.target, f.short, f.def, f.helpTxt)
		fs.StringVar(f.target, f.long, f.def, f.helpTxt)
	}
	fs.IntVar(&o.Retries, "retries", 60, "Max patch attempts")
	fs.IntVar(&o.RetryInterval, "retry-interval", 5, "Seconds between attempts")

	if err := fs.Parse(args); err != nil {
		return o, err
	}
	for _, req := range []struct{ val, name string }{
		{o.Namespace, "--namespace"},
		{o.SecretName, "--secret-name"},
		{o.ResourceType, "--resource-type"},
		{o.ResourceName, "--resource-name"},
	} {
		if req.val == "" {
			fmt.Fprintf(errOut, "%s required\n", req.name)
			fmt.Fprint(errOut, patchUsage)
			return o, fmt.Errorf("%s required", req.name)
		}
	}
	if o.ResourceType != ResourceAPIService && o.ResourceType != ResourceVWC {
		return o, fmt.Errorf("--resource-type must be 'apiservice' or 'vwc', got %q", o.ResourceType)
	}
	return o, nil
}

func Patch(ctx context.Context, kc kubernetes.Interface, agg aggregator.Interface, o PatchOptions) error {
	secret, err := kc.CoreV1().Secrets(o.Namespace).Get(ctx, o.SecretName, metav1.GetOptions{})
	if err != nil {
		return fmt.Errorf("get secret %s/%s: %w", o.Namespace, o.SecretName, err)
	}
	// client-go pre-decodes secret.Data, so the wire value the shell script read
	// from jq is reproduced by encoding these raw bytes exactly once.
	caRaw := secret.Data[o.CAName]
	if len(caRaw) == 0 {
		return fmt.Errorf("no %q key in secret %s/%s", o.CAName, o.Namespace, o.SecretName)
	}
	caBundle := base64.StdEncoding.EncodeToString(caRaw)

	patchType, body, err := patchBody(o.ResourceType, caBundle)
	if err != nil {
		return err
	}

	for attempt := 1; attempt <= o.Retries; attempt++ {
		err = applyPatch(ctx, kc, agg, o, patchType, body)
		if err == nil {
			logCertificate("patched caBundle", caRaw)
			slog.Info("patched resource", "type", o.ResourceType, "name", o.ResourceName)
			return nil
		}
		slog.Error("patch attempt failed", "attempt", attempt, "retries", o.Retries, "error", err)
		if attempt < o.Retries {
			time.Sleep(time.Duration(o.RetryInterval) * time.Second)
		}
	}
	return fmt.Errorf("patch failed after %d attempts: %w", o.Retries, err)
}

func patchBody(resourceType, caBundle string) (types.PatchType, []byte, error) {
	switch resourceType {
	case ResourceAPIService:
		body, err := json.Marshal(map[string]any{
			"spec": map[string]any{
				"caBundle":              caBundle,
				"insecureSkipTLSVerify": false,
			},
		})
		return types.MergePatchType, body, err
	case ResourceVWC:
		body, err := json.Marshal([]map[string]any{{
			"op":    "add",
			"path":  "/webhooks/0/clientConfig/caBundle",
			"value": caBundle,
		}})
		return types.JSONPatchType, body, err
	default:
		return "", nil, fmt.Errorf("unsupported resource type %q", resourceType)
	}
}

func applyPatch(ctx context.Context, kc kubernetes.Interface, agg aggregator.Interface, o PatchOptions, patchType types.PatchType, body []byte) error {
	switch o.ResourceType {
	case ResourceAPIService:
		_, err := agg.ApiregistrationV1().APIServices().Patch(ctx, o.ResourceName, patchType, body, metav1.PatchOptions{})
		return err
	case ResourceVWC:
		_, err := kc.AdmissionregistrationV1().ValidatingWebhookConfigurations().Patch(ctx, o.ResourceName, patchType, body, metav1.PatchOptions{})
		return err
	default:
		return fmt.Errorf("unsupported resource type %q", o.ResourceType)
	}
}
