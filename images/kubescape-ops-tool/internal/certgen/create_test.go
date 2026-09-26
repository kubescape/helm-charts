package certgen

import (
	"context"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"io"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

func baseCreateOptions(outDir string) CreateOptions {
	return CreateOptions{
		Namespace:  "kubescape",
		SecretName: "storage-certs",
		Hosts:      "storage.kubescape.svc,storage.kubescape.svc.cluster.local",
		OutDir:     outDir,
		CAName:     "ca",
		CertName:   "cert",
		KeyName:    "key",
		Days:       36500,
	}
}

func TestParseCreateFlagsDefaults(t *testing.T) {
	o, err := ParseCreateFlags([]string{
		"-n", "kubescape", "-s", "storage-certs",
		"-H", "storage.kubescape.svc", "-o", "/tmp/out",
	}, io.Discard)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if o.CAName != "ca" || o.CertName != "cert" || o.KeyName != "key" || o.Days != 36500 {
		t.Fatalf("unexpected defaults: %+v", o)
	}

	long, err := ParseCreateFlags([]string{
		"--namespace", "ns", "--secret-name", "s", "--host", "h", "--out-dir", "/tmp/o",
		"--ca-name", "CA", "--cert-name", "C", "--key-name", "K", "--days", "1",
	}, io.Discard)
	if err != nil {
		t.Fatalf("parse long: %v", err)
	}
	if long.CAName != "CA" || long.CertName != "C" || long.KeyName != "K" || long.Days != 1 {
		t.Fatalf("long flags not applied: %+v", long)
	}
}

func TestParseCreateFlagsRequired(t *testing.T) {
	if _, err := ParseCreateFlags([]string{"-n", "ns"}, io.Discard); err == nil {
		t.Fatal("expected error for missing required flags")
	}
}

func TestParseCreateFlagsDays(t *testing.T) {
	for _, days := range []int{1, 36500, 73000, 0, -1, 73001, 106752, math.MaxInt} {
		t.Run(strconv.Itoa(days), func(t *testing.T) {
			var errOut strings.Builder
			o, err := ParseCreateFlags([]string{
				"-n", "ns", "-s", "s", "-H", "h", "-o", "/tmp/out",
				"--days", strconv.Itoa(days),
			}, &errOut)
			if days < 1 || days > 73000 {
				if err == nil || !strings.Contains(err.Error(), "--days must be between 1 and 73000") {
					t.Fatalf("expected days range error, got %v", err)
				}
				if !strings.Contains(errOut.String(), err.Error()) || !strings.Contains(errOut.String(), createUsage) {
					t.Fatalf("expected range diagnostic and usage, got %q", errOut.String())
				}
				return
			}
			if err != nil {
				t.Fatalf("parse: %v", err)
			}
			if o.Days != days {
				t.Fatalf("Days = %d, want %d", o.Days, days)
			}
		})
	}
}

func TestCreateReusesExistingSecret(t *testing.T) {
	outDir := filepath.Join(t.TempDir(), "certs")
	o := baseCreateOptions(outDir)

	kc := fake.NewSimpleClientset(&corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: o.SecretName, Namespace: o.Namespace},
		Data: map[string][]byte{
			"ca":   []byte("ca-pem"),
			"cert": []byte("cert-pem"),
			"key":  []byte("key-pem"),
		},
	})

	if err := Create(context.Background(), kc, o); err != nil {
		t.Fatalf("Create: %v", err)
	}
	for name, want := range map[string]string{"cert": "cert-pem", "key": "key-pem"} {
		got, err := os.ReadFile(filepath.Join(outDir, name))
		if err != nil {
			t.Fatalf("read %s: %v", name, err)
		}
		if string(got) != want {
			t.Fatalf("%s = %q, want %q", name, got, want)
		}
	}
	for _, a := range kc.Actions() {
		if a.GetVerb() == "create" {
			t.Fatal("reuse path must not create a secret")
		}
	}
}

func TestCreateReuseFailsOnMissingKeys(t *testing.T) {
	o := baseCreateOptions(t.TempDir())
	kc := fake.NewSimpleClientset(&corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: o.SecretName, Namespace: o.Namespace},
		Data:       map[string][]byte{"ca": []byte("ca-pem")},
	})
	if err := Create(context.Background(), kc, o); err == nil {
		t.Fatal("expected error when cert/key keys are absent")
	}
}

func TestCreateGeneratesCAAndLeaf(t *testing.T) {
	outDir := filepath.Join(t.TempDir(), "certs")
	o := baseCreateOptions(outDir)
	kc := fake.NewSimpleClientset()

	if err := Create(context.Background(), kc, o); err != nil {
		t.Fatalf("Create: %v", err)
	}

	secret, err := kc.CoreV1().Secrets(o.Namespace).Get(context.Background(), o.SecretName, metav1.GetOptions{})
	if err != nil {
		t.Fatalf("secret not created: %v", err)
	}
	for _, k := range []string{o.CAName, o.CertName, o.KeyName} {
		if len(secret.Data[k]) == 0 {
			t.Fatalf("secret key %q empty", k)
		}
	}

	onDisk, err := os.ReadFile(filepath.Join(outDir, o.CertName))
	if err != nil {
		t.Fatalf("read cert file: %v", err)
	}
	if string(onDisk) != string(secret.Data[o.CertName]) {
		t.Fatal("on-disk cert differs from the secret's cert")
	}

	leaf := parseCert(t, secret.Data[o.CertName])
	ca := parseCert(t, secret.Data[o.CAName])

	if leaf.Subject.CommonName != "storage.kubescape.svc" {
		t.Fatalf("CN = %q", leaf.Subject.CommonName)
	}
	wantSANs := []string{"storage.kubescape.svc", "storage.kubescape.svc.cluster.local"}
	if len(leaf.DNSNames) != len(wantSANs) {
		t.Fatalf("DNS SANs = %v", leaf.DNSNames)
	}
	for i, want := range wantSANs {
		if leaf.DNSNames[i] != want {
			t.Fatalf("DNS SAN %d = %q, want %q", i, leaf.DNSNames[i], want)
		}
	}
	if leaf.KeyUsage != x509.KeyUsageDigitalSignature|x509.KeyUsageKeyEncipherment {
		t.Fatalf("key usage = %v", leaf.KeyUsage)
	}
	if len(leaf.ExtKeyUsage) != 1 || leaf.ExtKeyUsage[0] != x509.ExtKeyUsageServerAuth {
		t.Fatalf("ext key usage = %v", leaf.ExtKeyUsage)
	}
	if !ca.IsCA {
		t.Fatal("CA certificate is not marked as a CA")
	}
	if len(ca.Subject.Organization) != 1 || ca.Subject.Organization[0] != "certgen-ca" {
		t.Fatalf("CA organization = %v", ca.Subject.Organization)
	}

	pool := x509.NewCertPool()
	pool.AddCert(ca)
	if _, err := leaf.Verify(x509.VerifyOptions{
		Roots:     pool,
		DNSName:   "storage.kubescape.svc",
		KeyUsages: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}); err != nil {
		t.Fatalf("leaf does not verify against the generated CA: %v", err)
	}
}

func TestCreatePropagatesUnexpectedGetError(t *testing.T) {
	o := baseCreateOptions(t.TempDir())
	kc := fake.NewSimpleClientset()
	kc.PrependReactor("get", "secrets", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, errors.New("forbidden")
	})
	if err := Create(context.Background(), kc, o); err == nil {
		t.Fatal("expected a non-NotFound get error to propagate")
	}
}

func parseCert(t *testing.T, pemBytes []byte) *x509.Certificate {
	t.Helper()
	block, _ := pem.Decode(pemBytes)
	if block == nil {
		t.Fatal("not PEM encoded")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		t.Fatalf("parse certificate: %v", err)
	}
	return cert
}
