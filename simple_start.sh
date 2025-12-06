#!/bin/bash

cd /home/dash/optidex

# Load NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  --no-use

# Use node
nvm use 20

# Load audio environment configuration
if [ -f "/home/dash/optidex/.bluetooth_audio_env.sh" ]; then
  echo "Loading audio environment..."
  . "/home/dash/optidex/.bluetooth_audio_env.sh"
fi

# Find the sound card index for wm8960soundcard
card_index=$(awk '/wm8960soundcard/ {print $1}' /proc/asound/cards | head -n1)
# Default to 1 if not found
if [ -z "$card_index" ]; then
  card_index=1
fi
echo "Using sound card index: $card_index"

# Adjust volume
echo "Setting speaker volume..."
amixer -c $card_index set Speaker 114 2>/dev/null || echo "Warning: Could not set volume"

# Start Python UI first in background
cd python && sudo python3 chatbot-ui.py &
PYTHON_PID=$!

# Wait for Python UI to start  
sleep 5

# Start Node.js backend with proper sound card index
cd /home/dash/optidex
echo "Starting Node.js backend with sound card index: $card_index"
SOUND_CARD_INDEX=$card_index yarn start &
NODE_PID=$!

# Wait for both processes
wait $PYTHON_PID $NODE_PID

