#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=whisplay.service
USER_UNIT_DIR="$HOME/.config/systemd/user"
WORKDIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$USER_UNIT_DIR"

cat >"$USER_UNIT_DIR/$SERVICE_NAME" <<UNIT
[Unit]
Description=Whisplay AI Chatbot (user)
Wants=network-online.target bluetooth.target pipewire.service pipewire-pulse.service
After=network-online.target bluetooth.target pipewire.service pipewire-pulse.service

[Service]
Type=simple
WorkingDirectory=$WORKDIR
# Use your repo's launcher; it sets audio and env correctly
ExecStart=/usr/bin/env bash $WORKDIR/run_chatbot.sh
Restart=on-failure
RestartSec=3
# Log to the user journal
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
UNIT

# Enable user lingering so the service starts at boot without login
if command -v loginctl >/dev/null 2>&1; then
  if [ "${SUDO_USER:-}" != "" ]; then
    sudo loginctl enable-linger "$SUDO_USER"
  else
    sudo loginctl enable-linger "$USER"
  fi
fi

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

echo "Installed and started $SERVICE_NAME as a user service."
echo "Check status: systemctl --user status $SERVICE_NAME"
echo "View logs:   journalctl --user -u $SERVICE_NAME -f"
