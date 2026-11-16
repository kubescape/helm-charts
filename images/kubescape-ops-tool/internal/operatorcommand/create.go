package operatorcommand

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/util/uuid"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
)

// GVR is the resource the operator watches for scan requests.
var GVR = schema.GroupVersionResource{Group: "kubescape.io", Version: "v1alpha1", Resource: "operatorcommands"}

// Options are the parsed flags of create-operator-command.
type Options struct {
	Namespace    string
	RequestBody  string
	GenerateName string
	OwnerJob     string
}

const usage = `Usage: kubescape-ops-tool create-operator-command [flags]
  -n, --namespace      Namespace to create the OperatorCommand objects in (required)
  -f, --request-body   Path to the request body JSON, {"commands": [...]} (required)
  -g, --generate-name  metadata.generateName prefix of the created objects (required)
      --owner-job      Job that owns the created objects (default: $JOB_NAME)
`

// ParseFlags mirrors the flags of the create-operator-command.sh script it replaces. The
// owner Job defaults to $JOB_NAME, which the CronJob templates set from the Job's label.
func ParseFlags(args []string, getenv func(string) string, errOut io.Writer) (Options, error) {
	o := Options{OwnerJob: getenv("JOB_NAME")}
	fs := flag.NewFlagSet("create-operator-command", flag.ContinueOnError)
	fs.SetOutput(errOut)
	fs.Usage = func() { fmt.Fprint(errOut, usage) }
	fs.StringVar(&o.Namespace, "namespace", "", "")
	fs.StringVar(&o.Namespace, "n", "", "")
	fs.StringVar(&o.RequestBody, "request-body", "", "")
	fs.StringVar(&o.RequestBody, "f", "", "")
	fs.StringVar(&o.GenerateName, "generate-name", "", "")
	fs.StringVar(&o.GenerateName, "g", "", "")
	fs.StringVar(&o.OwnerJob, "owner-job", o.OwnerJob, "")
	if err := fs.Parse(args); err != nil {
		return o, err
	}
	for _, req := range []struct{ val, name string }{
		{o.Namespace, "--namespace"},
		{o.RequestBody, "--request-body"},
		{o.GenerateName, "--generate-name"},
	} {
		if req.val == "" {
			fmt.Fprintf(errOut, "%s required\n", req.name)
			fmt.Fprint(errOut, usage)
			return o, fmt.Errorf("%s required", req.name)
		}
	}
	return o, nil
}

type requestBody struct {
	Commands []json.RawMessage `json:"commands"`
}

// jobID returns the command's jobTracking.jobID the way the script's
// `jq -r '.jobTracking.jobID // empty'` did: keys match exactly, a string is used as it is,
// another non-null value as its JSON text, and null, false or an empty string as missing.
func jobID(command json.RawMessage) (string, error) {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(command, &fields); err != nil {
		return "", err
	}
	var tracking map[string]json.RawMessage
	if raw, ok := fields["jobTracking"]; ok && string(raw) != "null" {
		if err := json.Unmarshal(raw, &tracking); err != nil {
			return "", fmt.Errorf("jobTracking: %w", err)
		}
	}
	raw, ok := tracking["jobID"]
	if !ok {
		return "", nil
	}
	var id any
	if err := json.Unmarshal(raw, &id); err != nil {
		return "", err
	}
	switch v := id.(type) {
	case nil:
		return "", nil
	case bool:
		if !v {
			return "", nil
		}
	case string:
		return v, nil
	}
	var compact bytes.Buffer
	if err := json.Compact(&compact, raw); err != nil {
		return "", err
	}
	return compact.String(), nil
}

// Create creates one OperatorCommand per entry of the request body's commands array, with
// the entry as the command body. Owning the objects by the Job lets Kubernetes
// garbage-collect them together with the Job history instead of leaving one
// OperatorCommand behind per run.
func Create(ctx context.Context, kc kubernetes.Interface, dc dynamic.Interface, o Options, newGUID func() string) error {
	raw, err := os.ReadFile(o.RequestBody)
	if err != nil {
		return fmt.Errorf("read request body: %w", err)
	}
	var req requestBody
	if err := json.Unmarshal(raw, &req); err != nil {
		return fmt.Errorf("%s: %w", o.RequestBody, err)
	}
	if len(req.Commands) == 0 {
		return fmt.Errorf("%s has no commands", o.RequestBody)
	}

	var owners []any
	if o.OwnerJob != "" {
		job, err := kc.BatchV1().Jobs(o.Namespace).Get(ctx, o.OwnerJob, metav1.GetOptions{})
		if err != nil {
			return fmt.Errorf("get owner job %s/%s: %w", o.Namespace, o.OwnerJob, err)
		}
		owners = []any{map[string]any{
			"apiVersion": "batch/v1",
			"kind":       "Job",
			"name":       job.Name,
			"uid":        string(job.UID),
		}}
	}

	for i, command := range req.Commands {
		var compact bytes.Buffer
		if err := json.Compact(&compact, command); err != nil {
			return fmt.Errorf("commands[%d]: %w", i, err)
		}
		guid, err := jobID(command)
		if err != nil {
			return fmt.Errorf("commands[%d]: %w", i, err)
		}
		if guid == "" {
			guid = newGUID()
		}

		metadata := map[string]any{
			"generateName": o.GenerateName,
			"namespace":    o.Namespace,
			"labels":       map[string]any{"kubescape.io/app-name": "operator"},
		}
		if owners != nil {
			metadata["ownerReferences"] = owners
		}
		obj := &unstructured.Unstructured{Object: map[string]any{
			"apiVersion": "kubescape.io/v1alpha1",
			"kind":       "OperatorCommand",
			"metadata":   metadata,
			"spec": map[string]any{
				"guid":        guid,
				"commandType": "OperatorAPI",
				"body":        base64.StdEncoding.EncodeToString(compact.Bytes()),
			},
		}}
		created, err := dc.Resource(GVR).Namespace(o.Namespace).Create(ctx, obj, metav1.CreateOptions{})
		if err != nil {
			return fmt.Errorf("create OperatorCommand %d of %d: %w", i+1, len(req.Commands), err)
		}
		slog.Info("created OperatorCommand", "namespace", o.Namespace, "name", created.GetName(), "guid", guid)
	}
	return nil
}

// NewGUID returns a random (version 4) UUID, as /proc/sys/kernel/random/uuid did for the
// script.
func NewGUID() string { return string(uuid.NewUUID()) }
