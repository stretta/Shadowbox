#!/usr/bin/env bash

set -e

usage() {
    cat <<EOF
Usage: ./install.sh [--display DISPLAY_BACKEND] [--no-start]

Options:
  --display DISPLAY_BACKEND  Set SHADOWBOX_DISPLAY for this install.
                             Example: waveshare_5inch_dsi
  --no-start                 Install the service but do not enable or start it.
                             Use when display/input hardware is not attached yet.
  -h, --help                 Show this help.

SHADOWBOX_DISPLAY can still be set in the environment. --display takes
precedence when both are provided.
EOF
}

DISPLAY_KIND="${SHADOWBOX_DISPLAY:-st7789_raw}"
START_SERVICE=1

install_status() {
    if [[ -n "${SHADOWBOX_INSTALL_STATUS_FILE:-}" ]]; then
        printf '%s\n' "$*" > "${SHADOWBOX_INSTALL_STATUS_FILE}" 2>/dev/null || true
    fi
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --display)
            if [[ "$#" -lt 2 || "$2" == -* ]]; then
                echo "Missing value for --display."
                usage
                exit 1
            fi
            DISPLAY_KIND="$2"
            shift 2
            ;;
        --display=*)
            DISPLAY_KIND="${1#*=}"
            if [[ -z "${DISPLAY_KIND}" ]]; then
                echo "Missing value for --display."
                usage
                exit 1
            fi
            shift
            ;;
        --no-start)
            START_SERVICE=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            usage
            exit 1
            ;;
    esac
done

export SHADOWBOX_DISPLAY="${DISPLAY_KIND}"

if [[ "${EUID}" -eq 0 ]]; then
    echo "Do not run install.sh with sudo."
    echo "Run it as your normal user from the repository root:"
    echo "./install.sh"
    exit 1
fi

cleanup_sudo_password_file() {
    if [[ -n "${SHADOWBOX_SUDO_PASSWORD_FILE:-}" && "${SHADOWBOX_SUDO_PASSWORD_FILE}" == /tmp/shadowbox-sudo.* ]]; then
        rm -f "${SHADOWBOX_SUDO_PASSWORD_FILE}"
    fi
}
trap cleanup_sudo_password_file EXIT

sudo() {
    if [[ -n "${SHADOWBOX_SUDO_PASSWORD_FILE:-}" && -f "${SHADOWBOX_SUDO_PASSWORD_FILE}" ]]; then
        command sudo -S -p "" -v < "${SHADOWBOX_SUDO_PASSWORD_FILE}" || return
    fi
    command sudo "$@"
}

REPO_DIR="$(pwd)"
RUN_USER="$(id -un)"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
SERVICE_PATH="/etc/systemd/system/shadowbox.service"
EARLY_SPLASH_SERVICE_PATH="/etc/systemd/system/shadowbox-early-splash.service"
DEFAULT_ENV_PATH="/etc/default/shadowbox"
ENABLE_SPI=1
ENABLE_PIGPIOD=1
FONT_SOURCE_DIR="${REPO_DIR}/assets/fonts"
FONT_INSTALL_DIR="/usr/local/share/fonts/shadowbox/ibm-plex"
DIRECT_ETHERNET_HELPER="${REPO_DIR}/tools/direct_ethernet.sh"
WIFI_NETWORK_HELPER="${REPO_DIR}/tools/wifi_network.sh"
HDMI_MIRROR_HELPER="${REPO_DIR}/tools/hdmi_mirror_config.py"
SYSTEM_POWER_HELPER="${REPO_DIR}/tools/system_power.py"
DIRECT_ETHERNET_SUDOERS_PATH="/etc/sudoers.d/shadowbox-direct-ethernet"
WIFI_NETWORK_SUDOERS_PATH="/etc/sudoers.d/shadowbox-wifi-network"
HDMI_MIRROR_SUDOERS_PATH="/etc/sudoers.d/shadowbox-hdmi-mirror"
SYSTEM_POWER_SUDOERS_PATH="/etc/sudoers.d/shadowbox-system-power"

case "${DISPLAY_KIND}" in
    waveshare_5inch_dsi)
        ENABLE_SPI=0
        ENABLE_PIGPIOD=0
        ;;
esac

boot_file_path() {
    local basename="$1"

    if sudo test -e "/boot/firmware/${basename}"; then
        printf '/boot/firmware/%s\n' "${basename}"
    elif sudo test -e "/boot/${basename}"; then
        printf '/boot/%s\n' "${basename}"
    else
        printf '/boot/firmware/%s\n' "${basename}"
    fi
}

configure_quiet_boot() {
    local boot_config_path
    local boot_cmdline_path
    local tmp_config
    local tmp_cmdline
    local current_cmdline
    local token
    local -a filtered_tokens

    boot_config_path="$(boot_file_path config.txt)"
    boot_cmdline_path="$(boot_file_path cmdline.txt)"

    echo "Suppressing Raspberry Pi boot graphics and console output..."

    tmp_config="$(mktemp)"
    if sudo test -f "${boot_config_path}"; then
        sudo cat "${boot_config_path}" > "${tmp_config}"
    fi
    if grep -q '^disable_splash=' "${tmp_config}"; then
        sed -i.bak 's/^disable_splash=.*/disable_splash=1/' "${tmp_config}"
        rm -f "${tmp_config}.bak"
    else
        {
            printf '\n'
            printf '# Shadowbox quiet boot\n'
            printf 'disable_splash=1\n'
        } >> "${tmp_config}"
    fi
    sudo install -m 0755 -d "$(dirname "${boot_config_path}")"
    sudo install -m 0644 "${tmp_config}" "${boot_config_path}"
    rm -f "${tmp_config}"

    if ! sudo test -f "${boot_cmdline_path}"; then
        echo "No boot cmdline found at ${boot_cmdline_path}; skipping console suppression."
        return
    fi

    current_cmdline="$(sudo cat "${boot_cmdline_path}")"
    filtered_tokens=()
    for token in ${current_cmdline}; do
        case "${token}" in
            console=tty0|console=tty1|console=tty2|console=tty3|console=tty4|console=tty5|console=tty6|quiet|splash|loglevel=*|logo.nologo|vt.global_cursor_default=*|systemd.show_status=*|rd.systemd.show_status=*|rd.udev.log_level=*|plymouth.enable=*|consoleblank=*)
                ;;
            *)
                filtered_tokens+=("${token}")
                ;;
        esac
    done

    filtered_tokens+=(
        "console=tty3"
        "quiet"
        "loglevel=0"
        "logo.nologo"
        "vt.global_cursor_default=0"
        "systemd.show_status=false"
        "rd.systemd.show_status=false"
        "rd.udev.log_level=0"
        "plymouth.enable=0"
        "consoleblank=0"
    )

    tmp_cmdline="$(mktemp)"
    printf '%s\n' "${filtered_tokens[*]}" > "${tmp_cmdline}"
    sudo install -m 0644 "${tmp_cmdline}" "${boot_cmdline_path}"
    rm -f "${tmp_cmdline}"
}

echo "Shadowbox installer"
echo "==================="
echo "Display backend: ${DISPLAY_KIND}"
install_status "starting"
if [[ "${START_SERVICE}" -eq 0 ]]; then
    echo "Service start: disabled for this install"
fi

echo "Updating system..."
install_status "apt update"
sudo apt update

echo "Installing system dependencies..."
install_status "system packages"
SYSTEM_PACKAGES=(
    python3-venv \
    python3-pip \
    fontconfig \
    libopenjp2-7 \
    libopenblas0
)

if [[ "${ENABLE_PIGPIOD}" -eq 1 ]]; then
    SYSTEM_PACKAGES+=(
        pigpio \
        python3-spidev \
        python3-rpi.gpio
    )
fi

if [[ "${DISPLAY_KIND}" == "waveshare_5inch_dsi" ]]; then
    SYSTEM_PACKAGES+=(python3-kms++)
fi

sudo apt install -y \
    "${SYSTEM_PACKAGES[@]}"

echo "Installing bundled IBM Plex fonts..."
install_status "fonts"
if compgen -G "${FONT_SOURCE_DIR}/*.ttf" >/dev/null; then
    sudo install -d -m 0755 "${FONT_INSTALL_DIR}"
    sudo install -m 0644 "${FONT_SOURCE_DIR}"/*.ttf "${FONT_INSTALL_DIR}/"
    sudo fc-cache -f "${FONT_INSTALL_DIR}"
else
    echo "No bundled fonts found in ${FONT_SOURCE_DIR}."
    exit 1
fi

case "${DISPLAY_KIND}" in
    ssd1306|ssd1309)
        echo "Installing OLED/I2C dependencies..."
        install_status "i2c setup"
        sudo apt install -y \
            python3-smbus \
            i2c-tools

        echo "Enabling I2C..."
        sudo raspi-config nonint do_i2c 0
        ;;
    st7789|st7789_raw|st7735s_hat|waveshare_2inch)
        echo "Skipping I2C setup for TFT display backend."
        ;;
    waveshare_5inch_dsi)
        echo "Skipping I2C/SPI setup for DSI display backend."
        ENABLE_SPI=0
        ;;
    *)
        echo "Unknown SHADOWBOX_DISPLAY='${DISPLAY_KIND}'."
        echo "Skipping display-specific I2C setup."
        ;;
esac

if [[ "${ENABLE_SPI}" -eq 1 ]]; then
    echo "Enabling SPI..."
    install_status "spi setup"
    sudo raspi-config nonint do_spi 0
fi

install_status "quiet boot"
configure_quiet_boot

if [[ "${DISPLAY_KIND}" == "waveshare_5inch_dsi" ]]; then
    echo "Reserving the primary framebuffer console for Shadowbox..."
    # The default tty1 getty can repaint the framebuffer while Shadowbox is
    # blocked on startup discovery. Keep SSH, the serial console, and alternate
    # virtual terminals available while preventing tty1 from competing with
    # the appliance UI.
    sudo systemctl mask --now getty@tty1.service
fi

if [[ "${ENABLE_PIGPIOD}" -eq 1 && "${START_SERVICE}" -eq 1 ]]; then
    echo "Starting pigpio daemon..."
    install_status "pigpio"
    sudo systemctl enable pigpiod
    sudo systemctl start pigpiod
elif [[ "${ENABLE_PIGPIOD}" -eq 1 ]]; then
    echo "Skipping pigpio daemon start because --no-start was provided."
else
    echo "Skipping pigpio daemon for DSI touch display backend."
fi

echo "Creating Python virtual environment..."
install_status "venv"
python3 -m venv .venv

echo "Activating venv..."
source .venv/bin/activate

echo "Installing Python dependencies..."
install_status "python deps"
pip install --upgrade pip
pip install -r requirements.txt

echo "Persisting Shadowbox environment..."
install_status "runtime config"
TMP_ENV="$(mktemp)"
if sudo test -f "${DEFAULT_ENV_PATH}"; then
    sudo cat "${DEFAULT_ENV_PATH}" > "${TMP_ENV}"
else
    cat > "${TMP_ENV}" <<EOF
# Shadowbox runtime configuration
# Generated by install.sh
EOF
fi

while IFS= read -r env_line; do
    key="${env_line%%=*}"
    if grep -q "^${key}=" "${TMP_ENV}"; then
        sed -i.bak "s|^${key}=.*|${env_line}|" "${TMP_ENV}"
        rm -f "${TMP_ENV}.bak"
    else
        printf '%s\n' "${env_line}" >> "${TMP_ENV}"
    fi
done < <(env | LC_ALL=C sort | grep '^SHADOWBOX_')

if ! grep -q '^SHADOWBOX_DISPLAY=' "${TMP_ENV}"; then
    printf 'SHADOWBOX_DISPLAY=%s\n' "${DISPLAY_KIND}" >> "${TMP_ENV}"
fi
if ! grep -q '^SHADOWBOX_DIRECT_ETHERNET_HELPER=' "${TMP_ENV}"; then
    printf 'SHADOWBOX_DIRECT_ETHERNET_HELPER=%s\n' "${DIRECT_ETHERNET_HELPER}" >> "${TMP_ENV}"
fi
if ! grep -q '^SHADOWBOX_WIFI_NETWORK_HELPER=' "${TMP_ENV}"; then
    printf 'SHADOWBOX_WIFI_NETWORK_HELPER=%s\n' "${WIFI_NETWORK_HELPER}" >> "${TMP_ENV}"
fi
if ! grep -q '^SHADOWBOX_HDMI_MIRROR_HELPER=' "${TMP_ENV}"; then
    printf 'SHADOWBOX_HDMI_MIRROR_HELPER=%s\n' "${HDMI_MIRROR_HELPER}" >> "${TMP_ENV}"
fi
if ! grep -q '^SHADOWBOX_SYSTEM_POWER_HELPER=' "${TMP_ENV}"; then
    printf 'SHADOWBOX_SYSTEM_POWER_HELPER=%s\n' "${SYSTEM_POWER_HELPER}" >> "${TMP_ENV}"
fi
if [[ "${DISPLAY_KIND}" == "waveshare_5inch_dsi" ]] && ! grep -q '^SHADOWBOX_DSI_HDMI_MIRROR=' "${TMP_ENV}"; then
    printf 'SHADOWBOX_DSI_HDMI_MIRROR=0\n' >> "${TMP_ENV}"
fi

sudo install -m 0644 "${TMP_ENV}" "${DEFAULT_ENV_PATH}"
rm -f "${TMP_ENV}"

echo "Configuring direct Ethernet helper..."
install_status "direct ethernet helper"
chmod 0755 "${DIRECT_ETHERNET_HELPER}"
TMP_SUDOERS="$(mktemp)"
cat > "${TMP_SUDOERS}" <<EOF
${RUN_USER} ALL=(root) NOPASSWD: ${DIRECT_ETHERNET_HELPER}
EOF
sudo visudo -cf "${TMP_SUDOERS}"
sudo install -m 0440 "${TMP_SUDOERS}" "${DIRECT_ETHERNET_SUDOERS_PATH}"
rm -f "${TMP_SUDOERS}"

echo "Configuring WiFi network helper..."
install_status "wifi helper"
chmod 0755 "${WIFI_NETWORK_HELPER}"
TMP_SUDOERS="$(mktemp)"
cat > "${TMP_SUDOERS}" <<EOF
${RUN_USER} ALL=(root) NOPASSWD: ${WIFI_NETWORK_HELPER}
EOF
sudo visudo -cf "${TMP_SUDOERS}"
sudo install -m 0440 "${TMP_SUDOERS}" "${WIFI_NETWORK_SUDOERS_PATH}"
rm -f "${TMP_SUDOERS}"

echo "Configuring HDMI mirror helper..."
chmod 0755 "${HDMI_MIRROR_HELPER}"
TMP_SUDOERS="$(mktemp)"
cat > "${TMP_SUDOERS}" <<EOF
${RUN_USER} ALL=(root) NOPASSWD: ${HDMI_MIRROR_HELPER} enable, ${HDMI_MIRROR_HELPER} disable, ${HDMI_MIRROR_HELPER} status
EOF
sudo visudo -cf "${TMP_SUDOERS}"
sudo install -m 0440 "${TMP_SUDOERS}" "${HDMI_MIRROR_SUDOERS_PATH}"
rm -f "${TMP_SUDOERS}"

echo "Configuring system power helper..."
chmod 0755 "${SYSTEM_POWER_HELPER}"
TMP_SUDOERS="$(mktemp)"
cat > "${TMP_SUDOERS}" <<EOF
${RUN_USER} ALL=(root) NOPASSWD: ${SYSTEM_POWER_HELPER} reboot
EOF
sudo visudo -cf "${TMP_SUDOERS}"
sudo install -m 0440 "${TMP_SUDOERS}" "${SYSTEM_POWER_SUDOERS_PATH}"
rm -f "${TMP_SUDOERS}"

echo "Installing systemd service..."
install_status "service"
PIGPIOD_UNIT_DEPENDENCIES=""
if [[ "${ENABLE_PIGPIOD}" -eq 1 ]]; then
    PIGPIOD_UNIT_DEPENDENCIES=$'Wants=pigpiod.service\nAfter=pigpiod.service'
fi

sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=Shadowbox RNBO Hardware UI
${PIGPIOD_UNIT_DEPENDENCIES}

[Service]
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} -m shadowbox.shadowbox
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/default/shadowbox
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

if [[ "${DISPLAY_KIND}" == "waveshare_5inch_dsi" ]]; then
    echo "Installing early DSI splash service..."
    sudo tee "${EARLY_SPLASH_SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=Shadowbox early DSI splash
DefaultDependencies=no
After=local-fs.target systemd-udev-trigger.service
Before=shadowbox.service

[Service]
Type=oneshot
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=-/etc/default/shadowbox
ExecStart=${VENV_PYTHON} ${REPO_DIR}/tools/early_framebuffer_splash.py
TimeoutStartSec=15

[Install]
WantedBy=multi-user.target
EOF
fi

sudo systemctl daemon-reload
if [[ "${START_SERVICE}" -eq 1 ]]; then
    if [[ "${DISPLAY_KIND}" == "waveshare_5inch_dsi" ]]; then
        sudo systemctl enable shadowbox-early-splash
    else
        sudo systemctl disable shadowbox-early-splash >/dev/null 2>&1 || true
    fi
    sudo systemctl enable shadowbox

    echo "Starting Shadowbox..."
    install_status "restart service"
    sudo systemctl restart shadowbox
else
    sudo systemctl disable shadowbox-early-splash >/dev/null 2>&1 || true
    sudo systemctl disable shadowbox >/dev/null 2>&1 || true
    echo "Shadowbox service installed but not enabled or started."
    echo "After attaching the display/input hardware, run:"
    if [[ "${DISPLAY_KIND}" == "waveshare_5inch_dsi" ]]; then
        echo "sudo systemctl enable shadowbox-early-splash"
    fi
    echo "sudo systemctl enable --now shadowbox"
fi

echo ""
echo "Install complete."
install_status "complete"
echo ""
echo "Reboot recommended:"
echo "sudo reboot"
echo ""
echo "Runtime configuration saved to ${DEFAULT_ENV_PATH}"
