package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"time"

	"helm.sh/helm/v3/pkg/action"
	"helm.sh/helm/v3/pkg/cli"

	"github.com/kubescape/helm-charts/images/kubescape-ops-tool/internal/certgen"
	"github.com/kubescape/helm-charts/images/kubescape-ops-tool/internal/helmupgrade"
	"github.com/kubescape/helm-charts/images/kubescape-ops-tool/internal/kube"
	"github.com/kubescape/helm-charts/images/kubescape-ops-tool/internal/rollout"
)

const rootUsage = `kubescape-ops-tool <subcommand> [flags]

Subcommands:
  certgen-create   Create or reuse a TLS secret and materialize its cert/key
  certgen-patch    Patch an APIService or ValidatingWebhookConfiguration caBundle
  rollout-restart  Restart a deployment the way "kubectl rollout restart" does
  helm-upgrade     Upgrade a Helm release from a chart repository
`

func main() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, nil)))

	if len(os.Args) < 2 {
		fmt.Fprint(os.Stderr, rootUsage)
		os.Exit(2)
	}

	args := os.Args[2:]
	var err error
	switch os.Args[1] {
	case "certgen-create":
		err = runCertgenCreate(args)
	case "certgen-patch":
		err = runCertgenPatch(args)
	case "rollout-restart":
		err = runRolloutRestart(args)
	case "helm-upgrade":
		err = runHelmUpgrade(args)
	case "-h", "--help", "help":
		fmt.Fprint(os.Stdout, rootUsage)
		return
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand: %s\n\n", os.Args[1])
		fmt.Fprint(os.Stderr, rootUsage)
		os.Exit(2)
	}

	if err != nil {
		slog.Error("command failed", "subcommand", os.Args[1], "error", err)
		os.Exit(1)
	}
}

func runCertgenCreate(args []string) error {
	o, err := certgen.ParseCreateFlags(args, os.Stderr)
	if err != nil {
		os.Exit(2)
	}
	cfg, err := kube.Config()
	if err != nil {
		return err
	}
	kc, err := kube.Kubernetes(cfg)
	if err != nil {
		return err
	}
	return certgen.Create(context.Background(), kc, o)
}

func runCertgenPatch(args []string) error {
	o, err := certgen.ParsePatchFlags(args, os.Stderr)
	if err != nil {
		os.Exit(2)
	}
	cfg, err := kube.Config()
	if err != nil {
		return err
	}
	kc, err := kube.Kubernetes(cfg)
	if err != nil {
		return err
	}
	agg, err := kube.Aggregator(cfg)
	if err != nil {
		return err
	}
	return certgen.Patch(context.Background(), kc, agg, o)
}

func runRolloutRestart(args []string) error {
	o, err := rollout.ParseFlags(args, os.Stderr)
	if err != nil {
		os.Exit(2)
	}
	cfg, err := kube.Config()
	if err != nil {
		return err
	}
	kc, err := kube.Kubernetes(cfg)
	if err != nil {
		return err
	}
	return rollout.Restart(context.Background(), kc, o, time.Now())
}

func runHelmUpgrade(args []string) error {
	o, err := helmupgrade.ParseFlags(args, os.Getenv, os.Stderr)
	if err != nil {
		os.Exit(2)
	}
	settings := cli.New()
	settings.SetNamespace(o.Namespace)

	actionConfig := new(action.Configuration)
	if err := actionConfig.Init(settings.RESTClientGetter(), o.Namespace, os.Getenv("HELM_DRIVER"), func(format string, v ...any) {
		slog.Info(fmt.Sprintf(format, v...))
	}); err != nil {
		return err
	}
	_, err = helmupgrade.Upgrade(actionConfig, settings, o)
	return err
}
