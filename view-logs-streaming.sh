#!/bin/bash
# Stream logs from the chatbot in real-time

echo "📊 Whisplay Chatbot Log Streaming"
echo "=================================="
echo ""

# Check which log source to use
if [ -f "chatbot.log" ]; then
    echo "✓ Found chatbot.log - streaming live logs..."
    echo ""
    echo "Press Ctrl+C to stop streaming"
    echo "=================================="
    echo ""
    tail -f chatbot.log
elif systemctl --user is-active --quiet whisplay.service; then
    echo "✓ Systemd service is running - streaming journalctl logs..."
    echo ""
    echo "Press Ctrl+C to stop streaming"
    echo "=================================="
    echo ""
    journalctl --user -u whisplay.service -f
else
    echo "❌ No logs found!"
    echo ""
    echo "Options:"
    echo "1. Start chatbot with logging:"
    echo "   ./run_chatbot.sh > chatbot.log 2>&1 &"
    echo ""
    echo "2. Start systemd service:"
    echo "   systemctl --user start whisplay.service"
    echo "   journalctl --user -u whisplay.service -f"
    echo ""
    echo "3. View existing log files:"
    echo "   tail -f chatbot.log"
    exit 1
fi


