#!/bin/bash
# View whisplay logs in real-time

echo "================================================"
echo "Whisplay AI Chatbot Logs"
echo "================================================"
echo ""
echo "Showing logs from the last 50 lines, then following in real-time..."
echo "Press Ctrl+C to stop"
echo ""
echo "================================================"
echo ""

journalctl --user -u whisplay.service -n 50 -f



