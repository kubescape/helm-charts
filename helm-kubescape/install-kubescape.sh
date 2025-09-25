#!/bin/bash
set -e

# Installation script for Kubescape Helm Plugin
# This script is run when the plugin is installed via 'helm plugin install'

PLUGIN_NAME="kubescape"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check if kubescape is installed
check_kubescape() {
    if command -v kubescape >/dev/null 2>&1; then
        local version=$(kubescape version --short 2>/dev/null || echo "unknown")
        print_success "Kubescape is already installed (version: $version)"
        return 0
    else
        return 1
    fi
}

# Install kubescape if not present
install_kubescape() {
    print_info "Kubescape not found in PATH. Attempting to install..."
    
    # Detect OS and architecture
    local os=$(uname -s | tr '[:upper:]' '[:lower:]')
    local arch=$(uname -m)
    
    case $arch in
        x86_64) arch="amd64" ;;
        aarch64|arm64) arch="arm64" ;;
        *) 
            print_error "Unsupported architecture: $arch"
            return 1
            ;;
    esac
    
    case $os in
        linux|darwin) ;;
        *)
            print_error "Unsupported operating system: $os"
            return 1
            ;;
    esac
    
    # Try to install kubescape using the official installer
    if command -v curl >/dev/null 2>&1; then
        print_info "Installing kubescape using curl..."
        if curl -s https://raw.githubusercontent.com/kubescape/kubescape/master/install.sh | /bin/bash; then
            print_success "Kubescape installed successfully"
            return 0
        else
            print_warning "Failed to install kubescape using the official installer"
        fi
    fi
    
    # Fallback: manual download
    print_info "Attempting manual download of kubescape..."
    local download_url="https://github.com/kubescape/kubescape/releases/latest/download/kubescape-${os}-${arch}"
    local install_dir="$HOME/.local/bin"
    local kubescape_bin="$install_dir/kubescape"
    
    # Create install directory if it doesn't exist
    mkdir -p "$install_dir"
    
    if command -v curl >/dev/null 2>&1; then
        if curl -L -o "$kubescape_bin" "$download_url"; then
            chmod +x "$kubescape_bin"
            print_success "Kubescape downloaded to $kubescape_bin"
            print_info "Please ensure $install_dir is in your PATH"
            return 0
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget -O "$kubescape_bin" "$download_url"; then
            chmod +x "$kubescape_bin"
            print_success "Kubescape downloaded to $kubescape_bin"
            print_info "Please ensure $install_dir is in your PATH"
            return 0
        fi
    fi
    
    print_error "Failed to download kubescape"
    return 1
}

# Main installation logic
main() {
    print_info "Installing Kubescape Helm Plugin..."
    
    # Check if kubescape is available
    if ! check_kubescape; then
        print_warning "Kubescape not found. The plugin will attempt to install it."
        print_info "You can also install kubescape manually from: https://github.com/kubescape/kubescape"
        
        # Attempt to install kubescape
        if ! install_kubescape; then
            print_warning "Could not automatically install kubescape."
            print_info "Please install kubescape manually:"
            print_info "  curl -s https://raw.githubusercontent.com/kubescape/kubescape/master/install.sh | /bin/bash"
            print_info "  or download from: https://github.com/kubescape/kubescape/releases"
        fi
    fi
    
    # Make sure the main script is executable
    chmod +x "$HELM_PLUGIN_DIR/kubescape.sh"
    
    print_success "Kubescape Helm Plugin installed successfully!"
    print_info "Usage: helm kubescape [CHART] [flags]"
    print_info "Help:  helm kubescape --help"
}

main "$@"