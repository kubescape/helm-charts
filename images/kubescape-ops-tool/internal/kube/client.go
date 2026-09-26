package kube

import (
	"fmt"
	"os"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	aggregator "k8s.io/kube-aggregator/pkg/client/clientset_generated/clientset"
)

// Config returns the in-cluster REST config, falling back to KUBECONFIG when
// the tool is run outside a pod.
func Config() (*rest.Config, error) {
	cfg, err := rest.InClusterConfig()
	if err == nil {
		return cfg, nil
	}
	if kubeconfig := os.Getenv("KUBECONFIG"); kubeconfig != "" {
		return clientcmd.BuildConfigFromFlags("", kubeconfig)
	}
	return nil, fmt.Errorf("no in-cluster config and no KUBECONFIG set: %w", err)
}

func Kubernetes(cfg *rest.Config) (*kubernetes.Clientset, error) {
	return kubernetes.NewForConfig(cfg)
}

func Aggregator(cfg *rest.Config) (*aggregator.Clientset, error) {
	return aggregator.NewForConfig(cfg)
}
