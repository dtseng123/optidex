#!/bin/bash
# Setup script for vision capabilities

echo "================================================"
echo "Vision Capabilities Setup"
echo "================================================"
echo ""

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if ollama is installed
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}⚠ Ollama not found${NC}"
    echo "Install with: curl -fsSL https://ollama.com/install.sh | sh"
    echo ""
fi

# Check system RAM
TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
echo "System RAM: ${TOTAL_RAM}GB"
echo ""

# Recommend models based on RAM
if [ "$TOTAL_RAM" -le 8 ]; then
    echo -e "${YELLOW}⚠ Low RAM detected (8GB or less)${NC}"
    echo "Recommended vision models for your system:"
    echo ""
    echo "  1. moondream      - BEST for 8GB, ~1.7GB, fast (RECOMMENDED)"
    echo "  2. llava-phi3     - Good quality, ~2.9GB"
    echo "  3. llava:7b       - Better quality, ~4.7GB (might be tight)"
    echo ""
    echo "NOT recommended:"
    echo "  ✗ llama3.2-vision:11b - Too large (~7GB)"
    echo ""
    RECOMMENDED_MODEL="moondream"
else
    echo "Recommended vision models:"
    echo "  1. moondream              - Fast, ~1.7GB (great for quick responses)"
    echo "  2. llava:7b               - Good quality, ~4.7GB"
    echo "  3. llama3.2-vision:11b    - Better quality, ~7GB"
    echo "  4. llama3.2-vision:90b    - Best quality, ~55GB (requires GPU)"
    echo ""
    RECOMMENDED_MODEL="llava:7b"
fi

# Check if recommended model is installed
if ollama list | grep -q "$RECOMMENDED_MODEL"; then
    echo -e "${GREEN}✓ $RECOMMENDED_MODEL already installed${NC}"
else
    echo -e "${YELLOW}⚠ $RECOMMENDED_MODEL not installed${NC}"
    echo ""
    read -p "Install $RECOMMENDED_MODEL? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing $RECOMMENDED_MODEL..."
        ollama pull $RECOMMENDED_MODEL
        echo -e "${GREEN}✓ Installation complete${NC}"
        
        # Update .env if it exists
        if [ -f .env ]; then
            if grep -q "OLLAMA_VISION_MODEL" .env; then
                sed -i "s/OLLAMA_VISION_MODEL=.*/OLLAMA_VISION_MODEL=$RECOMMENDED_MODEL/" .env
            else
                echo "OLLAMA_VISION_MODEL=$RECOMMENDED_MODEL" >> .env
            fi
            echo -e "${GREEN}✓ Updated .env with OLLAMA_VISION_MODEL=$RECOMMENDED_MODEL${NC}"
        fi
    else
        echo "Skipping installation. You can install later with:"
        echo "  ollama pull $RECOMMENDED_MODEL"
    fi
fi

echo ""
echo "================================================"
echo "Setup Complete"
echo "================================================"
echo ""
echo -e "${BLUE}Vision Tools Available:${NC}"
echo "  • analyzeImage - Analyze photos"
echo "  • analyzeVideoFrame - Analyze video content"
echo ""
echo -e "${BLUE}How to Use:${NC}"
echo ""
echo "1. Take a photo:"
echo "   Say: 'Take a picture'"
echo ""
echo "2. Analyze it:"
echo "   Say: 'What do you see in the picture?'"
echo "   Say: 'Describe what's in the image'"
echo "   Say: 'Is there any text in the photo?'"
echo ""
echo "3. Record and analyze video:"
echo "   Say: 'Record a 5 second video'"
echo "   Say: 'What's in the video?'"
echo "   Say: 'Describe what you saw in the video'"
echo ""
echo -e "${BLUE}Models Used:${NC}"
echo "  • Online: GPT-4o (OpenAI Vision)"
echo "  • Offline: llama3.2-vision:11b (Ollama)"
echo ""
echo "Restart chatbot to enable:"
echo "  systemctl --user restart whisplay.service"
echo ""

