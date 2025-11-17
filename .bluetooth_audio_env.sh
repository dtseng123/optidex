#!/usr/bin/env bash
# Ensure this process and children talk to the user's Pulse/PipeWire server
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export PULSE_RUNTIME_PATH="$XDG_RUNTIME_DIR/pulse"
export PULSE_SERVER="unix:$PULSE_RUNTIME_PATH/native"

# Wait for PulseAudio/PipeWire to be ready (max ~30s)
for i in $(seq 1 30); do
  if pactl info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Find a Bluetooth sink (bluez_output...) and set it as process-preferred sink
BT_SINK=""
for i in $(seq 1 30); do
  BT_SINK=$(pactl list short sinks 2>/dev/null | awk '/bluez_output/{print $2}' | head -n1)
  if [ -n "$BT_SINK" ]; then
    break
  fi
  sleep 1
done

if [ -n "$BT_SINK" ]; then
  export PULSE_SINK="$BT_SINK"
fi

# Force ALSA clients (aplay/mpg123 via ALSA) to use Pulse plugin
export AUDIO_OUTPUT_DEVICE="pulse"
