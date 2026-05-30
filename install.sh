#!/usr/bin/env bash

set -e

if [[ "${EUID}" -eq 0 ]]; then
    echo "Do not run install.sh with sudo."
    echo "Run it as your normal user from the repository root:"
    echo "./install.sh"
    exit 1
fi

REPO_DIR="$(pwd)"
RUN_USER="$(id -un)"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
SERVICE_PATH="/etc/systemd/system/shadowbox.service"
DEFAULT_ENV_PATH="/etc/default/shadowbox"
DISPLAY_KIND="${SHADOWBOX_DISPLAY:-st7789_raw}"
ENABLE_SPI=1
FONT_SOURCE_DIR="${REPO_DIR}/assets/fonts"
FONT_INSTALL_DIR="/usr/local/share/fonts/shadowbox/ibm-plex"
DIRECT_ETHERNET_HELPER="${REPO_DIR}/tools/direct_ethernet.sh"
SUDOERS_PATH="/etc/sudoers.d/shadowbox-direct-ethernet"

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

echo "Updating system..."
sudo apt update

echo "Installing system dependencies..."
sudo apt install -y \
    python3-venv \
    python3-pip \
    pigpio \
    fontconfig \
    libopenjp2-7 \
    libopenblas0 \
    python3-spidev \
    python3-rpi.gpio

echo "Installing bundled IBM Plex fonts..."
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
    sudo raspi-config nonint do_spi 0
fi

configure_quiet_boot

echo "Starting pigpio daemon..."
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

echo "Creating Python virtual environment..."
python3 -m venv .venv

echo "Activating venv..."
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Persisting Shadowbox environment..."
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

sudo install -m 0644 "${TMP_ENV}" "${DEFAULT_ENV_PATH}"
rm -f "${TMP_ENV}"

echo "Configuring direct Ethernet helper..."
chmod 0755 "${DIRECT_ETHERNET_HELPER}"
TMP_SUDOERS="$(mktemp)"
cat > "${TMP_SUDOERS}" <<EOF
${RUN_USER} ALL=(root) NOPASSWD: ${DIRECT_ETHERNET_HELPER}
EOF
sudo visudo -cf "${TMP_SUDOERS}"
sudo install -m 0440 "${TMP_SUDOERS}" "${SUDOERS_PATH}"
rm -f "${TMP_SUDOERS}"

echo "Installing systemd service..."
sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=Shadowbox RNBO Hardware UI
Wants=pigpiod.service
After=network.target pigpiod.service

[Service]
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} -m shadowbox.shadowbox
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/default/shadowbox

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable shadowbox

echo "Starting Shadowbox..."
sudo systemctl restart shadowbox

echo ""
echo "Install complete."
echo ""
echo "Reboot recommended:"
echo "sudo reboot"
echo ""
echo "Runtime configuration saved to ${DEFAULT_ENV_PATH}"
