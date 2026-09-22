package certgen

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type CreateOptions struct {
	Namespace  string
	SecretName string
	Hosts      string
	OutDir     string
	CAName     string
	CertName   string
	KeyName    string
	Days       int
}

// ParseCreateFlags mirrors charts/kubescape-operator/scripts/certgen-create.sh's flag surface.
func ParseCreateFlags(args []string, errOut io.Writer) (CreateOptions, error) {
	var o CreateOptions
	fs := flag.NewFlagSet("certgen-create", flag.ContinueOnError)
	fs.SetOutput(errOut)
	fs.Usage = func() { fmt.Fprint(errOut, createUsage) }

	for _, f := range []struct {
		target       *string
		short, long  string
		def, helpTxt string
	}{
		{&o.Namespace, "n", "namespace", "", "Namespace for the secret (required)"},
		{&o.SecretName, "s", "secret-name", "", "Name of the secret to read/create (required)"},
		{&o.Hosts, "H", "host", "", "Comma-separated DNS SANs for the leaf cert (required)"},
		{&o.OutDir, "o", "out-dir", "", "Directory to write the leaf cert/key into (required)"},
		{&o.CAName, "", "ca-name", "ca", "Key in the secret for the CA cert"},
		{&o.CertName, "", "cert-name", "cert", "Key in the secret for the leaf cert"},
		{&o.KeyName, "", "key-name", "key", "Key in the secret for the leaf key"},
	} {
		if f.short != "" {
			fs.StringVar(f.target, f.short, f.def, f.helpTxt)
		}
		fs.StringVar(f.target, f.long, f.def, f.helpTxt)
	}
	fs.IntVar(&o.Days, "days", 36500, "Validity in days (1-73000)")

	if err := fs.Parse(args); err != nil {
		return o, err
	}
	if o.Days < 1 || o.Days > 73000 {
		fmt.Fprintln(errOut, "--days must be between 1 and 73000")
		fmt.Fprint(errOut, createUsage)
		return o, fmt.Errorf("--days must be between 1 and 73000")
	}
	for _, req := range []struct{ val, name string }{
		{o.Namespace, "--namespace"},
		{o.SecretName, "--secret-name"},
		{o.Hosts, "--host"},
		{o.OutDir, "--out-dir"},
	} {
		if req.val == "" {
			fmt.Fprintf(errOut, "%s required\n", req.name)
			fmt.Fprint(errOut, createUsage)
			return o, fmt.Errorf("%s required", req.name)
		}
	}
	return o, nil
}

const createUsage = `Usage: kubescape-ops-tool certgen-create [flags]
  -n, --namespace      Namespace for the secret (required)
  -s, --secret-name    Name of the secret to read/create (required)
  -H, --host           Comma-separated DNS SANs for the leaf cert (required)
  -o, --out-dir        Directory to write the leaf cert/key into (required)
      --ca-name        Key in the secret for the CA cert (default: ca)
      --cert-name      Key in the secret for the leaf cert (default: cert)
      --key-name       Key in the secret for the leaf key (default: key)
      --days           Validity in days, 1-73000 (default: 36500 ~= 100y)
`

func Create(ctx context.Context, kc kubernetes.Interface, o CreateOptions) error {
	if err := os.MkdirAll(o.OutDir, 0o755); err != nil {
		return fmt.Errorf("create out-dir %s: %w", o.OutDir, err)
	}

	secret, err := kc.CoreV1().Secrets(o.Namespace).Get(ctx, o.SecretName, metav1.GetOptions{})
	switch {
	case err == nil:
		return reuseSecret(secret, o)
	case apierrors.IsNotFound(err):
		return generate(ctx, kc, o)
	default:
		return fmt.Errorf("get secret %s/%s: %w", o.Namespace, o.SecretName, err)
	}
}

func reuseSecret(secret *corev1.Secret, o CreateOptions) error {
	slog.Info("secret exists, reusing", "namespace", o.Namespace, "secret", o.SecretName)

	certPEM := secret.Data[o.CertName]
	keyPEM := secret.Data[o.KeyName]
	if len(certPEM) == 0 || len(keyPEM) == 0 {
		return fmt.Errorf("secret missing %s/%s", o.CertName, o.KeyName)
	}
	if err := os.WriteFile(filepath.Join(o.OutDir, o.CertName), certPEM, 0o644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(o.OutDir, o.KeyName), keyPEM, 0o600); err != nil {
		return err
	}
	logCertificate("reused leaf certificate", certPEM)
	return nil
}

func generate(ctx context.Context, kc kubernetes.Interface, o CreateOptions) error {
	slog.Info("secret not found, generating", "namespace", o.Namespace, "secret", o.SecretName)

	hosts := splitHosts(o.Hosts)
	if len(hosts) == 0 {
		return fmt.Errorf("--host produced no DNS names")
	}
	notBefore := time.Now().Add(-time.Minute)
	notAfter := notBefore.Add(time.Duration(o.Days) * 24 * time.Hour)

	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	caSerial, err := serialNumber()
	if err != nil {
		return err
	}
	caTemplate := &x509.Certificate{
		SerialNumber:          caSerial,
		Subject:               pkix.Name{Organization: []string{"certgen-ca"}},
		NotBefore:             notBefore,
		NotAfter:              notAfter,
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTemplate, caTemplate, &caKey.PublicKey, caKey)
	if err != nil {
		return err
	}
	caCert, err := x509.ParseCertificate(caDER)
	if err != nil {
		return err
	}

	leafKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	leafSerial, err := serialNumber()
	if err != nil {
		return err
	}
	leafTemplate := &x509.Certificate{
		SerialNumber: leafSerial,
		Subject:      pkix.Name{CommonName: hosts[0]},
		DNSNames:     hosts,
		NotBefore:    notBefore,
		NotAfter:     notAfter,
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, leafTemplate, caCert, &leafKey.PublicKey, caKey)
	if err != nil {
		return err
	}

	caPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER})
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: leafDER})
	leafKeyDER, err := x509.MarshalECPrivateKey(leafKey)
	if err != nil {
		return err
	}
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: leafKeyDER})

	if err := os.WriteFile(filepath.Join(o.OutDir, o.CertName), certPEM, 0o644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(o.OutDir, o.KeyName), keyPEM, 0o600); err != nil {
		return err
	}

	_, err = kc.CoreV1().Secrets(o.Namespace).Create(ctx, &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: o.SecretName, Namespace: o.Namespace},
		Type:       corev1.SecretTypeOpaque,
		Data: map[string][]byte{
			o.CAName:   caPEM,
			o.CertName: certPEM,
			o.KeyName:  keyPEM,
		},
	}, metav1.CreateOptions{})
	if err != nil {
		return fmt.Errorf("create secret %s/%s: %w", o.Namespace, o.SecretName, err)
	}

	logCertificate("generated leaf certificate", certPEM)
	return nil
}

func splitHosts(hosts string) []string {
	var out []string
	for _, h := range strings.Split(hosts, ",") {
		if h = strings.TrimSpace(h); h != "" {
			out = append(out, h)
		}
	}
	return out
}

func serialNumber() (*big.Int, error) {
	limit := new(big.Int).Lsh(big.NewInt(1), 128)
	return rand.Int(rand.Reader, limit)
}

// logCertificate replaces the `kubectl exec -- openssl x509 -text` debugging path
// that the shell-free image no longer offers.
func logCertificate(msg string, certPEM []byte) {
	block, _ := pem.Decode(certPEM)
	if block == nil {
		return
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return
	}
	slog.Info(msg,
		"subject", cert.Subject.String(),
		"dnsNames", strings.Join(cert.DNSNames, ","),
		"notAfter", cert.NotAfter.Format(time.RFC3339),
	)
}
