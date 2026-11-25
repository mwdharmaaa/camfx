#!/bin/bash
# ==============================================================================
# CamFX Automated Installation Script (mirrors Commanda pipeline)
# Build, Test, Package .deb, Purge Old Version, Install & Enable v4l2loopback.
# ==============================================================================

set -euo pipefail

COLOR_RESET="\033[0m"
COLOR_BOLD="\033[1m"
COLOR_CYAN="\033[36m"
COLOR_GREEN="\033[32m"
COLOR_YELLOW="\033[33m"
COLOR_RED="\033[31m"
COLOR_BLUE="\033[34m"

log_step() { echo -e "${COLOR_BOLD}${COLOR_CYAN}[STEP]${COLOR_RESET} $1"; }
log_info() { echo -e "${COLOR_BLUE}[INFO]${COLOR_RESET} $1"; }
log_warn() { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $1"; }
log_success() { echo -e "${COLOR_BOLD}${COLOR_GREEN}[SUCCESS]${COLOR_RESET} $1"; }
log_error() { echo -e "${COLOR_BOLD}${COLOR_RED}[ERROR]${COLOR_RESET} $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${COLOR_BOLD}==============================================================================${COLOR_RESET}"
echo -e "${COLOR_BOLD}                    CAMFX AUTOMATED INSTALLATION PIPELINE                     ${COLOR_RESET}"
echo -e "${COLOR_BOLD}==============================================================================${COLOR_RESET}"

log_step "Verifying system prerequisites..."
for cmd in python3 make dpkg-deb dpkg apt; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_error "Required dependency '$cmd' is not installed."
        exit 1
    fi
done

APP_VERSION="$(python3 -c "import camfx; print(camfx.__version__)")"
log_info "Application : camfx (v${APP_VERSION})"

log_step "Running automated pipeline and effect test suite..."
PYTHONPATH=. python3 -m unittest discover -s tests -v

log_step "Building Debian (.deb) package..."
make package

DEB_FILE="$(find output/deb -name "camfx_${APP_VERSION}_amd64.deb" 2>/dev/null | head -n 1)"
if [ -z "$DEB_FILE" ] || [ ! -f "$DEB_FILE" ]; then
    log_error "Failed to locate generated .deb package in output/deb/"
    exit 1
fi
chmod 644 "$DEB_FILE"
log_info "Debian package created: $DEB_FILE ($(du -h "$DEB_FILE" | cut -f1))"

log_step "Acquiring sudo privileges for system installation..."
if [ "$EUID" -ne 0 ]; then
    sudo -v
fi

if dpkg -s camfx >/dev/null 2>&1; then
    log_warn "Purging previous installation of camfx..."
    sudo apt purge -y camfx || sudo dpkg -P camfx
fi

log_step "Installing $(basename "$DEB_FILE")..."
sudo apt install -y --reinstall "./$DEB_FILE"

log_step "Verifying v4l2loopback virtual camera module..."
if ! lsmod | grep -q "^v4l2loopback"; then
    sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="CamFX Virtual Camera" exclusive_caps=1 || true
fi

if [ -e /dev/video10 ]; then
    log_info "Virtual Camera Ready: /dev/video10 ($(cat /sys/class/video4linux/video10/name 2>/dev/null || echo 'CamFX Virtual Camera'))"
else
    log_warn "/dev/video10 not detected yet. Check 'sudo modprobe v4l2loopback devices=1 video_nr=10 card_label=\"CamFX Virtual Camera\" exclusive_caps=1'."
fi

echo ""
echo -e "${COLOR_BOLD}==============================================================================${COLOR_RESET}"
log_success "CamFX v${APP_VERSION} installed! Launch with:"
echo -e "  ${COLOR_CYAN}camfx${COLOR_RESET}                              (Buka CamFX Studio GUI)"
echo -e "  ${COLOR_CYAN}camfx --headless --effect cyberpunk${COLOR_RESET} (Jalan di terminal/background)"
echo -e "  ${COLOR_CYAN}camfx --list-effects${COLOR_RESET}               (Lihat semua efek)"
echo -e "  ${COLOR_CYAN}camfx --list-devices${COLOR_RESET}               (Cek kamera & virtual camera)"
echo -e "${COLOR_BOLD}==============================================================================${COLOR_RESET}"
