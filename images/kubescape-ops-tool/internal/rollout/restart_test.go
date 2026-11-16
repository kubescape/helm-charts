package rollout

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"testing"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

func TestParseFlags(t *testing.T) {
	o, err := ParseFlags([]string{"--namespace", "kubescape", "--deployment", "grype-offline-db"}, io.Discard)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if o.Namespace != "kubescape" || o.Deployment != "grype-offline-db" {
		t.Fatalf("unexpected options: %+v", o)
	}
	if _, err := ParseFlags([]string{"--namespace", "kubescape"}, io.Discard); err == nil {
		t.Fatal("expected error when --deployment is missing")
	}
}

func TestRestartPatchesRestartedAtAnnotation(t *testing.T) {
	o := Options{Namespace: "kubescape", Deployment: "grype-offline-db"}
	kc := fake.NewSimpleClientset(&appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{Name: o.Deployment, Namespace: o.Namespace},
	})
	now := time.Date(2026, 9, 20, 10, 30, 0, 0, time.UTC)

	if err := Restart(context.Background(), kc, o, now); err != nil {
		t.Fatalf("Restart: %v", err)
	}

	var patch k8stesting.PatchAction
	for _, a := range kc.Actions() {
		if p, ok := a.(k8stesting.PatchAction); ok {
			patch = p
		}
	}
	if patch == nil {
		t.Fatal("no patch action recorded")
	}
	if patch.GetNamespace() != o.Namespace || patch.GetName() != o.Deployment {
		t.Fatalf("patched %s/%s", patch.GetNamespace(), patch.GetName())
	}
	if patch.GetPatchType() != types.StrategicMergePatchType {
		t.Fatalf("patch type = %v", patch.GetPatchType())
	}

	var body struct {
		Spec struct {
			Template struct {
				Metadata struct {
					Annotations map[string]string `json:"annotations"`
				} `json:"metadata"`
			} `json:"template"`
		} `json:"spec"`
	}
	if err := json.Unmarshal(patch.GetPatch(), &body); err != nil {
		t.Fatalf("unmarshal patch: %v", err)
	}
	if got := body.Spec.Template.Metadata.Annotations[RestartedAtAnnotation]; got != now.Format(time.RFC3339) {
		t.Fatalf("%s = %q", RestartedAtAnnotation, got)
	}
}

func TestRestartPropagatesPatchError(t *testing.T) {
	kc := fake.NewSimpleClientset()
	kc.PrependReactor("patch", "deployments", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, errors.New("deployment not found")
	})
	err := Restart(context.Background(), kc, Options{Namespace: "kubescape", Deployment: "missing"}, time.Now())
	if err == nil {
		t.Fatal("expected the patch error to propagate")
	}
}
