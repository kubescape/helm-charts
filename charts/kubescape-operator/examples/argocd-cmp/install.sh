#!/bin/bash
# Installation script for the Kubescape Helm Lookup CMP plugin for ArgoCD
# This script sets up the Config Management Plugin to enable Helm lookup function support

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGOCD_NAMESPACE="${ARGOCD_NAMESPACE:-argocd}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi

    if ! kubectl get namespace "$ARGOCD_NAMESPACE" &> /dev/null; then
        log_error "ArgoCD namespace '$ARGOCD_NAMESPACE' not found. Is ArgoCD installed?"
        exit 1
    fi

    if ! kubectl get deployment argocd-repo-server -n "$ARGOCD_NAMESPACE" &> /dev/null; then
        log_error "argocd-repo-server deployment not found in '$ARGOCD_NAMESPACE'"
        exit 1
    fi

    log_info "Prerequisites check passed"
}

# Install the CMP plugin
install_cmp() {
    log_info "Installing CMP plugin ConfigMap..."
    kubectl apply -f "$SCRIPT_DIR/cmp-plugin-configmap.yaml"

    log_info "Installing RBAC permissions..."
    kubectl apply -f "$SCRIPT_DIR/rbac.yaml"

    log_info "Patching argocd-repo-server deployment..."

    # Check if the sidecar already exists
    EXISTING_CONTAINER=$(kubectl get deployment argocd-repo-server -n "$ARGOCD_NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[?(@.name=="kubescape-helm-lookup")].name}' 2>/dev/null || true)

    if [ -n "$EXISTING_CONTAINER" ]; then
        log_warn "CMP sidecar 'kubescape-helm-lookup' already exists, skipping patch"
    else
        # Apply the patch using strategic merge patch
        kubectl patch deployment argocd-repo-server -n "$ARGOCD_NAMESPACE" \
            --type=strategic \
            --patch-file="$SCRIPT_DIR/repo-server-patch.yaml"
    fi

    log_info "Waiting for argocd-repo-server to be ready..."
    kubectl rollout status deployment/argocd-repo-server -n "$ARGOCD_NAMESPACE" --timeout=300s

    log_info "CMP plugin installed successfully!"
}

# Uninstall the CMP plugin
uninstall_cmp() {
    log_info "Uninstalling CMP plugin..."

    # Remove the sidecar container from the deployment
    log_info "Removing CMP sidecar from argocd-repo-server..."

    # Get current containers and filter out the CMP sidecar
    kubectl get deployment argocd-repo-server -n "$ARGOCD_NAMESPACE" -o json | \
        jq 'del(.spec.template.spec.containers[] | select(.name == "kubescape-helm-lookup"))' | \
        jq 'del(.spec.template.spec.volumes[] | select(.name == "cmp-kubescape" or .name == "cmp-tmp"))' | \
        kubectl apply -f - || log_warn "Could not remove sidecar, it may not exist"

    log_info "Removing RBAC permissions..."
    kubectl delete -f "$SCRIPT_DIR/rbac.yaml" --ignore-not-found

    log_info "Removing CMP plugin ConfigMap..."
    kubectl delete -f "$SCRIPT_DIR/cmp-plugin-configmap.yaml" --ignore-not-found

    log_info "Waiting for argocd-repo-server to be ready..."
    kubectl rollout status deployment/argocd-repo-server -n "$ARGOCD_NAMESPACE" --timeout=300s

    log_info "CMP plugin uninstalled successfully!"
}

# Verify the installation
verify_installation() {
    log_info "Verifying CMP plugin installation..."

    # Check if the sidecar is running
    SIDECAR_STATUS=$(kubectl get pods -n "$ARGOCD_NAMESPACE" -l app.kubernetes.io/name=argocd-repo-server \
        -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="kubescape-helm-lookup")].ready}' 2>/dev/null || echo "false")

    if [ "$SIDECAR_STATUS" = "true" ]; then
        log_info "CMP sidecar is running and ready"
    else
        log_warn "CMP sidecar is not ready yet. Check pod status:"
        kubectl get pods -n "$ARGOCD_NAMESPACE" -l app.kubernetes.io/name=argocd-repo-server
    fi

    # Check RBAC
    log_info "Verifying RBAC permissions..."
    if kubectl auth can-i list nodes --as=system:serviceaccount:"$ARGOCD_NAMESPACE":argocd-repo-server &> /dev/null; then
        log_info "RBAC permissions are correctly configured"
    else
        log_error "RBAC permissions are not correctly configured"
        log_error "The argocd-repo-server service account cannot list nodes"
    fi

    # Check ConfigMap
    if kubectl get configmap cmp-kubescape-helm-lookup -n "$ARGOCD_NAMESPACE" &> /dev/null; then
        log_info "CMP ConfigMap exists"
    else
        log_error "CMP ConfigMap not found"
    fi
}

# Show usage
usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  install     Install the CMP plugin (default)"
    echo "  uninstall   Uninstall the CMP plugin"
    echo "  verify      Verify the installation"
    echo "  help        Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  ARGOCD_NAMESPACE   ArgoCD namespace (default: argocd)"
    echo ""
    echo "Example:"
    echo "  $0 install"
    echo "  ARGOCD_NAMESPACE=argocd-system $0 install"
}

# Main
main() {
    case "${1:-install}" in
        install)
            check_prerequisites
            install_cmp
            verify_installation
            echo ""
            log_info "Next steps:"
            echo "  1. Create an ArgoCD Application using the plugin:"
            echo "     kubectl apply -f $SCRIPT_DIR/application.yaml"
            echo ""
            echo "  2. Or modify your existing Application to use the plugin:"
            echo "     spec:"
            echo "       source:"
            echo "         plugin:"
            echo "           name: kubescape-helm-lookup-v1.0"
            ;;
        uninstall)
            check_prerequisites
            uninstall_cmp
            ;;
        verify)
            check_prerequisites
            verify_installation
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log_error "Unknown command: $1"
            usage
            exit 1
            ;;
    esac
}

main "$@"
