#!/bin/bash
set -euo pipefail

# Ensure whisper and other user-installed binaries are in PATH
export PATH="/home/dash/.local/bin:$PATH"

# Force both input and output to use PipeWire (pulse) for reliable audio routing
export AUDIO_INPUT_DEVICE="pulse"
export AUDIO_OUTPUT_DEVICE="pulse"

# PID file location
PIDFILE="/tmp/whisplay_chatbot.pid"

# Check if already running
if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE")
  # Check if the process is actually running
  if ps -p "$OLD_PID" > /dev/null 2>&1; then
    echo "ERROR: Chatbot is already running (PID: $OLD_PID)"
    echo "If you're sure it's not running, remove $PIDFILE and try again"
    exit 1
  else
    echo "Found stale PID file, removing..."
    rm -f "$PIDFILE"
  fi
fi

# Write our PID
echo $$ > "$PIDFILE"

# Initialize serve_ollama variable (will be set properly later from .env)
serve_ollama=false

# Cleanup function to remove PID file on exit
cleanup() {
  rm -f "$PIDFILE"
  echo "Cleaning up after service..."
  
  if [ "$serve_ollama" = true ]; then
    echo "Stopping Ollama server..."
    pkill ollama || true
  fi
  
  echo "===== Service ended: $(date) ====="
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Set working directory
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# Bluetooth/Pulse audio routing env (check if file exists first)
if [ -f "/home/dash/optidex/.bluetooth_audio_env.sh" ]; then
  . "/home/dash/optidex/.bluetooth_audio_env.sh"
elif [ -f "/home/dash/whisplay-ai-chatbot/.bluetooth_audio_env.sh" ]; then
  . "/home/dash/whisplay-ai-chatbot/.bluetooth_audio_env.sh"
else
  echo "Warning: Bluetooth audio env file not found, skipping..."
fi


# Find the sound card index for wm8960soundcard
card_index=$(awk '/wm8960soundcard/ {print $1}' /proc/asound/cards | head -n1)
# Default to 1 if not found
if [ -z "$card_index" ]; then
  card_index=1
fi
echo "Using sound card index: $card_index"

# Output current environment information (for debugging)
echo "===== Start time: $(date) =====" 
echo "Current user: $(whoami)" 
echo "Working directory: $(pwd)" 
working_dir=$(pwd)
echo "PATH: $PATH" 
echo "Python version: $(python3 --version)" 
echo "Node version: $(node --version)"
sleep 2
# Adjust volume
amixer -c $card_index set Speaker 114
# Start the service
echo "Starting Node.js application..."
cd $working_dir

# load .env variables, exclude comments and empty lines
# check if .env file exists
if [ -f ".env" ]; then
  # Load only SERVE_OLLAMA from .env (ignore comments/other vars)
  if grep -Eq '^[[:space:]]*SERVE_OLLAMA[[:space:]]*=' .env; then
    val=$(grep -E '^[[:space:]]*SERVE_OLLAMA[[:space:]]*=' .env | tail -n1 | cut -d'=' -f2-)
    # trim whitespace and surrounding quotes
    SERVE_OLLAMA=$(echo "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
    export SERVE_OLLAMA
  fi
  echo ".env variables loaded."
  # check if SERVE_OLLAMA is set to true
  if [ "$SERVE_OLLAMA" = "true" ]; then
    serve_ollama=true
  fi
else
  echo ".env file not found, please create one based on .env.template."
  exit 1
fi

if [ "$serve_ollama" = true ]; then
  echo "Starting Ollama server..."
  ollama serve &
fi

# Start Python UI first in background
echo "Starting Python UI..."
cd /home/dash/optidex/python && sudo python3 chatbot-ui.py &
PYTHON_PID=$!

# Wait for Python UI to start
sleep 5

# Start Node.js backend
cd /home/dash/optidex
echo "Starting Node.js backend with sound card index: $card_index"
SOUND_CARD_INDEX="$card_index" yarn start &
NODE_PID=$!

# Wait for both processes
wait $PYTHON_PID $NODE_PID
