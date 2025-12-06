#!/bin/bash

# Wrapper script to ensure environment is properly set up for systemd

# Set up PATH - include .local/bin for whisper
export PATH="/home/dash/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Load NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Ensure we're in the right directory
cd /home/dash/optidex || exit 1

# Check if required commands are available
if ! command -v node &> /dev/null; then
    echo "ERROR: node not found in PATH"
    exit 1
fi

if ! command -v yarn &> /dev/null; then
    echo "ERROR: yarn not found in PATH"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found in PATH"
    exit 1
fi

if ! command -v whisper &> /dev/null; then
    echo "ERROR: whisper not found in PATH"
    exit 1
fi

# Now run the actual chatbot script
exec bash /home/dash/optidex/run_chatbot.sh



