package operatorcommand

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	batchv1 "k8s.io/api/batch/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

func env(vars map[string]string) func(string) string {
	return func(k string) string { return vars[k] }
}

func TestParseFlags(t *testing.T) {
	o, err := ParseFlags([]string{"-n", "kubescape", "-f", "/home/ks/request-body.json", "-g", "kubescape-scheduler-"},
		env(map[string]string{"JOB_NAME": "kubescape-scheduler-29893209"}), io.Discard)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	want := Options{Namespace: "kubescape", RequestBody: "/home/ks/request-body.json",
		GenerateName: "kubescape-scheduler-", OwnerJob: "kubescape-scheduler-29893209"}
	if o != want {
		t.Fatalf("got %+v, want %+v", o, want)
	}

	o, err = ParseFlags([]string{"--namespace", "kubescape", "--request-body", "b.json", "--generate-name", "x-",
		"--owner-job", "manual"}, env(map[string]string{"JOB_NAME": "from-env"}), io.Discard)
	if err != nil {
		t.Fatalf("parse long flags: %v", err)
	}
	if o.OwnerJob != "manual" {
		t.Fatalf("--owner-job did not override $JOB_NAME: %q", o.OwnerJob)
	}

	for missing, args := range map[string][]string{
		"--namespace":     {"--request-body", "b.json", "--generate-name", "x-"},
		"--request-body":  {"--namespace", "kubescape", "--generate-name", "x-"},
		"--generate-name": {"--namespace", "kubescape", "--request-body", "b.json"},
	} {
		var errOut strings.Builder
		_, err := ParseFlags(args, env(nil), &errOut)
		if err == nil || !strings.HasPrefix(errOut.String(), missing+" required\n") {
			t.Fatalf("missing %s: err = %v, output = %q", missing, err, errOut.String())
		}
	}
}

// The cases follow the script's `jq -r '.jobTracking.jobID // empty'`.
func TestJobID(t *testing.T) {
	for command, want := range map[string]string{
		`{"jobTracking": {"jobID": "abc"}}`:   "abc",
		`{"jobTracking": {"jobID": 123}}`:     "123",
		`{"jobTracking": {"jobID": true}}`:    "true",
		`{"jobTracking": {"jobID": ""}}`:      "",
		`{"jobTracking": {"jobID": null}}`:    "",
		`{"jobTracking": {"jobID": false}}`:   "",
		`{"jobTracking": {"jobId": "lower"}}`: "",
		`{"jobTracking": null}`:               "",
		`{"CommandName": "kubescapeScan"}`:    "",
	} {
		got, err := jobID(json.RawMessage(command))
		if err != nil || got != want {
			t.Errorf("jobID(%s) = %q, %v; want %q", command, got, err, want)
		}
	}
	for _, command := range []string{`"scan"`, `{"jobTracking": "abc"}`} {
		if _, err := jobID(json.RawMessage(command)); err == nil {
			t.Errorf("jobID(%s): expected an error", command)
		}
	}
}

func writeBody(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "request-body.json")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

// clients returns a typed client holding the owner Job and a dynamic client that records
// every created OperatorCommand. The fake tracker does not resolve generateName, so the
// reactor stands in for the API server and names the object itself.
func clients(t *testing.T, objs ...runtime.Object) (*fake.Clientset, *dynamicfake.FakeDynamicClient, *[]*unstructured.Unstructured) {
	t.Helper()
	kc := fake.NewSimpleClientset(objs...)
	dc := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(runtime.NewScheme(),
		map[schema.GroupVersionResource]string{GVR: "OperatorCommandList"})
	var created []*unstructured.Unstructured
	dc.PrependReactor("create", "operatorcommands", func(a k8stesting.Action) (bool, runtime.Object, error) {
		obj := a.(k8stesting.CreateAction).GetObject().(*unstructured.Unstructured).DeepCopy()
		obj.SetName(obj.GetGenerateName() + "abcde")
		created = append(created, obj)
		return true, obj, nil
	})
	return kc, dc, &created
}

func TestCreateOneObjectPerCommand(t *testing.T) {
	job := &batchv1.Job{ObjectMeta: metav1.ObjectMeta{
		Name: "kubescape-scheduler-29893209", Namespace: "kubescape", UID: types.UID("8c1a"),
	}}
	kc, dc, created := clients(t, job)
	body := writeBody(t, `{"commands": [
		{"CommandName": "kubescapeScan", "jobTracking": {"jobID": "fixed-guid"}, "args": {"scanV1": {"targetType": "framework", "targetNames": ["nsa"]}}},
		{"CommandName": "kubescapeScan", "args": {"scanV1": {}}}
	]}`)
	o := Options{Namespace: "kubescape", RequestBody: body, GenerateName: "kubescape-scheduler-", OwnerJob: job.Name}

	if err := Create(context.Background(), kc, dc, o, func() string { return "generated-guid" }); err != nil {
		t.Fatalf("Create: %v", err)
	}
	if len(*created) != 2 {
		t.Fatalf("created %d OperatorCommands, want 2", len(*created))
	}

	first := (*created)[0]
	if first.GetAPIVersion() != "kubescape.io/v1alpha1" || first.GetKind() != "OperatorCommand" {
		t.Fatalf("created %s %s", first.GetAPIVersion(), first.GetKind())
	}
	if first.GetGenerateName() != "kubescape-scheduler-" || first.GetNamespace() != "kubescape" {
		t.Fatalf("generateName %q namespace %q", first.GetGenerateName(), first.GetNamespace())
	}
	if first.GetLabels()["kubescape.io/app-name"] != "operator" {
		t.Fatalf("labels = %v", first.GetLabels())
	}
	refs := first.GetOwnerReferences()
	if len(refs) != 1 || refs[0].Kind != "Job" || refs[0].APIVersion != "batch/v1" ||
		refs[0].Name != job.Name || refs[0].UID != job.UID {
		t.Fatalf("ownerReferences = %+v", refs)
	}

	spec := func(obj *unstructured.Unstructured, field string) string {
		v, _, _ := unstructured.NestedString(obj.Object, "spec", field)
		return v
	}
	if spec(first, "commandType") != "OperatorAPI" {
		t.Fatalf("commandType = %q", spec(first, "commandType"))
	}
	if spec(first, "guid") != "fixed-guid" {
		t.Fatalf("guid from jobTracking = %q", spec(first, "guid"))
	}
	if spec((*created)[1], "guid") != "generated-guid" {
		t.Fatalf("guid without jobTracking = %q", spec((*created)[1], "guid"))
	}

	// The body is the command entry with its whitespace removed.
	decoded, err := base64.StdEncoding.DecodeString(spec(first, "body"))
	if err != nil {
		t.Fatalf("body is not base64: %v", err)
	}
	want := `{"CommandName":"kubescapeScan","jobTracking":{"jobID":"fixed-guid"},"args":{"scanV1":{"targetType":"framework","targetNames":["nsa"]}}}`
	if string(decoded) != want {
		t.Fatalf("body = %s\nwant   %s", decoded, want)
	}
}

func TestCreateWithoutOwnerJob(t *testing.T) {
	kc, dc, created := clients(t)
	o := Options{Namespace: "kubescape", RequestBody: writeBody(t, `{"commands":[{"CommandName":"kubescapeScan"}]}`),
		GenerateName: "x-"}
	if err := Create(context.Background(), kc, dc, o, func() string { return "g" }); err != nil {
		t.Fatalf("Create: %v", err)
	}
	if len(*created) != 1 || len((*created)[0].GetOwnerReferences()) != 0 {
		t.Fatalf("want one object without owner references, got %d: %+v", len(*created), *created)
	}
}

func TestCreateRejectsBadRequestBodies(t *testing.T) {
	for name, body := range map[string]string{
		"no commands array": `{"other": []}`,
		"empty commands":    `{"commands": []}`,
		"not json":          `commands`,
	} {
		t.Run(name, func(t *testing.T) {
			kc, dc, created := clients(t)
			o := Options{Namespace: "kubescape", RequestBody: writeBody(t, body), GenerateName: "x-"}
			if err := Create(context.Background(), kc, dc, o, func() string { return "g" }); err == nil {
				t.Fatal("expected an error")
			}
			if len(*created) != 0 {
				t.Fatalf("created %d objects from a bad body", len(*created))
			}
		})
	}
}

func TestCreateFailsWhenOwnerJobIsMissing(t *testing.T) {
	kc, dc, created := clients(t)
	o := Options{Namespace: "kubescape", RequestBody: writeBody(t, `{"commands":[{}]}`),
		GenerateName: "x-", OwnerJob: "gone"}
	err := Create(context.Background(), kc, dc, o, func() string { return "g" })
	if err == nil || !strings.Contains(err.Error(), "owner job") {
		t.Fatalf("err = %v", err)
	}
	if len(*created) != 0 {
		t.Fatalf("created %d objects without an owner", len(*created))
	}
}

func TestCreatePropagatesCreateError(t *testing.T) {
	kc := fake.NewSimpleClientset()
	dc := dynamicfake.NewSimpleDynamicClientWithCustomListKinds(runtime.NewScheme(),
		map[schema.GroupVersionResource]string{GVR: "OperatorCommandList"})
	dc.PrependReactor("create", "operatorcommands", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, errors.New("operatorcommands.kubescape.io is forbidden")
	})
	o := Options{Namespace: "kubescape", RequestBody: writeBody(t, `{"commands":[{}]}`), GenerateName: "x-"}
	err := Create(context.Background(), kc, dc, o, func() string { return "g" })
	if err == nil || !strings.Contains(err.Error(), "forbidden") {
		t.Fatalf("err = %v", err)
	}
}
