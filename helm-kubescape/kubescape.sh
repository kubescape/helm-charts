#!/bin/bash
set -e

# Kubescape Helm Plugin
# This plugin renders Helm charts and scans them with Kubescape

PLUGIN_NAME="kubescape"
PLUGIN_VERSION="1.0.0"

# Color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Print usage information
print_usage() {
    cat << EOF
Kubescape Helm Plugin v${PLUGIN_VERSION}

USAGE:
    helm kubescape [CHART] [flags]

DESCRIPTION:
    Scan Helm charts with Kubescape security scanner.
    
    This plugin renders Helm charts using 'helm template' and then runs Kubescape 
    security scans on the resulting Kubernetes manifests. It supports all standard 
    Helm chart arguments including --values, --set, and --set-string flags.

ARGUMENTS:
    CHART       Path to chart directory, chart archive, or chart reference

FLAGS:
    -h, --help                    Show this help message
    -v, --verbose                 Enable verbose output
    --version                     Show plugin version
    --values value-files          Specify values in a YAML file (can specify multiple)
    --set stringArray             Set values on the command line (can specify multiple)
    --set-string stringArray      Set STRING values on the command line (can specify multiple)
    --set-file stringArray        Set values from respective files specified via the command line
    --release-name string         Release name for the chart (default: "kubescape-scan")
    --namespace string            Namespace scope for the chart (default: "default")
    --kubescape-args string       Additional arguments to pass to kubescape scan
    --keep-manifests             Keep the rendered manifests after scanning
    --output-dir string          Directory to save scan results and manifests

EXAMPLES:
    # Scan a local chart
    helm kubescape ./my-chart
    
    # Scan a chart with custom values
    helm kubescape ./my-chart --values values.yaml
    
    # Scan a chart with set overrides
    helm kubescape ./my-chart --set image.tag=latest
    
    # Scan a remote chart
    helm kubescape bitnami/nginx --repo https://charts.bitnami.com/bitnami
    
    # Scan with custom kubescape arguments
    helm kubescape ./my-chart --kubescape-args "--severity high,critical"
    
    # Keep manifests and specify output directory
    helm kubescape ./my-chart --keep-manifests --output-dir ./scan-results

EOF
}

# Check if required tools are installed
check_dependencies() {
    if ! command -v helm >/dev/null 2>&1; then
        print_error "helm is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v kubescape >/dev/null 2>&1; then
        print_error "kubescape is not installed or not in PATH"
        print_info "Install kubescape with: curl -s https://raw.githubusercontent.com/kubescape/kubescape/master/install.sh | /bin/bash"
        exit 1
    fi
}

# Parse command line arguments
parse_args() {
    CHART=""
    VERBOSE=false
    KEEP_MANIFESTS=false
    RELEASE_NAME="kubescape-scan"
    NAMESPACE="default"
    OUTPUT_DIR=""
    KUBESCAPE_ARGS=""
    HELM_ARGS=()
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                print_usage
                exit 0
                ;;
            --version)
                echo "Kubescape Helm Plugin v${PLUGIN_VERSION}"
                exit 0
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            --values)
                HELM_ARGS+=("--values" "$2")
                shift 2
                ;;
            --set)
                HELM_ARGS+=("--set" "$2")
                shift 2
                ;;
            --set-string)
                HELM_ARGS+=("--set-string" "$2")
                shift 2
                ;;
            --set-file)
                HELM_ARGS+=("--set-file" "$2")
                shift 2
                ;;
            --release-name)
                RELEASE_NAME="$2"
                shift 2
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --kubescape-args)
                KUBESCAPE_ARGS="$2"
                shift 2
                ;;
            --keep-manifests)
                KEEP_MANIFESTS=true
                shift
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --repo)
                HELM_ARGS+=("--repo" "$2")
                shift 2
                ;;
            -*)
                print_error "Unknown flag: $1"
                print_usage
                exit 1
                ;;
            *)
                if [[ -z "$CHART" ]]; then
                    CHART="$1"
                else
                    print_error "Multiple charts specified: $CHART and $1"
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    if [[ -z "$CHART" ]]; then
        print_error "Chart not specified"
        print_usage
        exit 1
    fi
}

# Create temporary directory for manifests
create_temp_dir() {
    if [[ -n "$OUTPUT_DIR" ]]; then
        TEMP_DIR="$OUTPUT_DIR"
        mkdir -p "$TEMP_DIR"
    else
        TEMP_DIR=$(mktemp -d)
    fi
    
    MANIFEST_FILE="$TEMP_DIR/manifests.yaml"
    
    if [[ "$VERBOSE" == "true" ]]; then
        print_info "Using directory: $TEMP_DIR"
    fi
}

# Clean up temporary files
cleanup() {
    if [[ "$KEEP_MANIFESTS" == "false" && -z "$OUTPUT_DIR" && -n "$TEMP_DIR" ]]; then
        if [[ "$VERBOSE" == "true" ]]; then
            print_info "Cleaning up temporary files: $TEMP_DIR"
        fi
        rm -rf "$TEMP_DIR"
    fi
}

# Run helm template to render the chart
render_chart() {
    print_info "Rendering chart: $CHART"
    
    local helm_cmd="helm template $RELEASE_NAME $CHART --namespace $NAMESPACE"
    
    # Add helm arguments
    for arg in "${HELM_ARGS[@]}"; do
        helm_cmd="$helm_cmd $arg"
    done
    
    if [[ "$VERBOSE" == "true" ]]; then
        print_info "Running: $helm_cmd"
    fi
    
    # Execute helm template and save to file
    if ! eval "$helm_cmd > '$MANIFEST_FILE'"; then
        print_error "Failed to render chart with helm template"
        cleanup
        exit 1
    fi
    
    # Check if manifests were generated
    if [[ ! -s "$MANIFEST_FILE" ]]; then
        print_error "No manifests generated from chart"
        cleanup
        exit 1
    fi
    
    local manifest_count=$(grep -c "^---" "$MANIFEST_FILE" 2>/dev/null || echo "0")
    print_success "Chart rendered successfully ($manifest_count manifests generated)"
    
    if [[ "$VERBOSE" == "true" ]]; then
        print_info "Manifests saved to: $MANIFEST_FILE"
    fi
}

# Run kubescape scan on the rendered manifests
run_kubescape_scan() {
    print_info "Running Kubescape security scan"
    
    local kubescape_cmd="kubescape scan $MANIFEST_FILE"
    
    # Add custom kubescape arguments if specified
    if [[ -n "$KUBESCAPE_ARGS" ]]; then
        kubescape_cmd="$kubescape_cmd $KUBESCAPE_ARGS"
    fi
    
    # Add output file if output directory is specified
    if [[ -n "$OUTPUT_DIR" ]]; then
        kubescape_cmd="$kubescape_cmd --format json --output '$OUTPUT_DIR/kubescape-results.json'"
    fi
    
    if [[ "$VERBOSE" == "true" ]]; then
        print_info "Running: $kubescape_cmd"
    fi
    
    # Execute kubescape scan
    if eval "$kubescape_cmd"; then
        print_success "Kubescape scan completed"
        if [[ -n "$OUTPUT_DIR" ]]; then
            print_info "Results saved to: $OUTPUT_DIR/kubescape-results.json"
        fi
    else
        local exit_code=$?
        print_warning "Kubescape scan completed with warnings (exit code: $exit_code)"
        print_info "This may indicate security issues were found. Check the output above for details."
    fi
}

# Main function
main() {
    # Set up error handling
    trap cleanup EXIT
    
    # Parse command line arguments
    parse_args "$@"
    
    # Check dependencies
    check_dependencies
    
    # Create temporary directory
    create_temp_dir
    
    # Render the chart
    render_chart
    
    # Run kubescape scan
    run_kubescape_scan
    
    if [[ "$KEEP_MANIFESTS" == "true" || -n "$OUTPUT_DIR" ]]; then
        print_info "Manifests preserved at: $MANIFEST_FILE"
    fi
}

# Run main function with all arguments
main "$@"