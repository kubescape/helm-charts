package certgen

import (
	"context"
	"encoding/base64"
	"errors"
	"io"
	"testing"

	admissionv1 "k8s.io/api/admissionregistration/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
	apiregv1 "k8s.io/kube-aggregator/pkg/apis/apiregistration/v1"
	aggfake "k8s.io/kube-aggregator/pkg/client/clientset_generated/clientset/fake"
)

// caPEM is the raw, already-decoded value client-go hands back from secret.Data.
var caPEM = []byte("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")

func secretWithCA(namespace, name string, data map[string][]byte) *corev1.Secret {
	return &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace},
		Data:       data,
	}
}

func basePatchOptions(resourceType, resourceName string) PatchOptions {
	return PatchOptions{
		Namespace:     "kubescape",
		SecretName:    "storage-certs",
		CAName:        "ca",
		ResourceType:  resourceType,
		ResourceName:  resourceName,
		Retries:       3,
		RetryInterval: 0,
	}
}

func TestParsePatchFlags(t *testing.T) {
	o, err := ParsePatchFlags([]string{
		"-n", "kubescape", "-s", "storage-certs",
		"-t", "apiservice", "-r", "v1beta1.spdx",
	}, io.Discard)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if o.CAName != "ca" || o.Retries != 60 || o.RetryInterval != 5 {
		t.Fatalf("unexpected defaults: %+v", o)
	}

	if _, err := ParsePatchFlags([]string{
		"--namespace", "ns", "--secret-name", "s",
		"--resource-type", "bogus", "--resource-name", "r",
	}, io.Discard); err == nil {
		t.Fatal("expected rejection of an unknown resource type")
	}

	if _, err := ParsePatchFlags([]string{"-n", "ns"}, io.Discard); err == nil {
		t.Fatal("expected error for missing required flags")
	}
}

func TestPatchAPIServiceEncodesCABundleExactlyOnce(t *testing.T) {
	o := basePatchOptions(ResourceAPIService, "v1beta1.spdx.softwarecomposition.kubescape.io")
	kc := fake.NewSimpleClientset(secretWithCA(o.Namespace, o.SecretName, map[string][]byte{"ca": caPEM}))
	agg := aggfake.NewSimpleClientset(&apiregv1.APIService{
		ObjectMeta: metav1.ObjectMeta{Name: o.ResourceName},
	})

	if err := Patch(context.Background(), kc, agg, o); err != nil {
		t.Fatalf("Patch: %v", err)
	}

	action := lastPatchAction(t, agg.Actions())
	if action.GetPatchType() != types.MergePatchType {
		t.Fatalf("patch type = %v", action.GetPatchType())
	}
	want := `{"spec":{"caBundle":"` + base64.StdEncoding.EncodeToString(caPEM) + `","insecureSkipTLSVerify":false}}`
	if got := string(action.GetPatch()); got != want {
		t.Fatalf("patch body =\n%s\nwant\n%s", got, want)
	}
}

func TestPatchVWCUsesJSONPatch(t *testing.T) {
	o := basePatchOptions(ResourceVWC, "kubescape-admission-webhook")
	kc := fake.NewSimpleClientset(
		secretWithCA(o.Namespace, o.SecretName, map[string][]byte{"ca": caPEM}),
		&admissionv1.ValidatingWebhookConfiguration{
			ObjectMeta: metav1.ObjectMeta{Name: o.ResourceName},
			Webhooks: []admissionv1.ValidatingWebhook{{
				Name:         "validate.kubescape.io",
				ClientConfig: admissionv1.WebhookClientConfig{Service: &admissionv1.ServiceReference{Namespace: o.Namespace, Name: "webhook"}},
			}},
		},
	)

	if err := Patch(context.Background(), kc, aggfake.NewSimpleClientset(), o); err != nil {
		t.Fatalf("Patch: %v", err)
	}

	action := lastPatchAction(t, kc.Actions())
	if action.GetPatchType() != types.JSONPatchType {
		t.Fatalf("patch type = %v", action.GetPatchType())
	}
	want := `[{"op":"add","path":"/webhooks/0/clientConfig/caBundle","value":"` +
		base64.StdEncoding.EncodeToString(caPEM) + `"}]`
	if got := string(action.GetPatch()); got != want {
		t.Fatalf("patch body =\n%s\nwant\n%s", got, want)
	}
}

func TestPatchRetriesThenFails(t *testing.T) {
	o := basePatchOptions(ResourceAPIService, "v1beta1.spdx")
	kc := fake.NewSimpleClientset(secretWithCA(o.Namespace, o.SecretName, map[string][]byte{"ca": caPEM}))
	agg := aggfake.NewSimpleClientset()

	attempts := 0
	agg.PrependReactor("patch", "apiservices", func(k8stesting.Action) (bool, runtime.Object, error) {
		attempts++
		return true, nil, errors.New("apiservice not ready")
	})

	err := Patch(context.Background(), kc, agg, o)
	if err == nil {
		t.Fatal("expected failure after retry exhaustion")
	}
	if attempts != o.Retries {
		t.Fatalf("attempts = %d, want %d", attempts, o.Retries)
	}
}

func TestPatchFailsWithoutCAKey(t *testing.T) {
	o := basePatchOptions(ResourceAPIService, "v1beta1.spdx")
	kc := fake.NewSimpleClientset(secretWithCA(o.Namespace, o.SecretName, map[string][]byte{"other": caPEM}))
	if err := Patch(context.Background(), kc, aggfake.NewSimpleClientset(), o); err == nil {
		t.Fatal("expected failure when the CA key is missing")
	}
}

func TestPatchFailsWhenSecretMissing(t *testing.T) {
	o := basePatchOptions(ResourceVWC, "wh")
	if err := Patch(context.Background(), fake.NewSimpleClientset(), aggfake.NewSimpleClientset(), o); err == nil {
		t.Fatal("expected failure when the secret does not exist")
	}
}

func lastPatchAction(t *testing.T, actions []k8stesting.Action) k8stesting.PatchAction {
	t.Helper()
	for i := len(actions) - 1; i >= 0; i-- {
		if p, ok := actions[i].(k8stesting.PatchAction); ok {
			return p
		}
	}
	t.Fatal("no patch action recorded")
	return nil
}
