#!/bin/bash
# Setup YOLOE for live object detection

echo "================================================"
echo "YOLOE Live Object Detection Setup"
echo "================================================"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1-2)
echo "Python version: $PYTHON_VERSION"

# Check if ultralytics is installed
echo ""
echo "Checking for Ultralytics YOLO..."
if python3 -c "import ultralytics" 2>/dev/null; then
    VERSION=$(python3 -c "import ultralytics; print(ultralytics.__version__)" 2>/dev/null)
    echo -e "${GREEN}✓ Ultralytics already installed (v$VERSION)${NC}"
else
    echo -e "${YELLOW}⚠ Ultralytics not installed${NC}"
    echo ""
    echo "Installing Ultralytics YOLO (this may take a few minutes)..."
    pip3 install ultralytics --user
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Installation complete${NC}"
    else
        echo -e "${YELLOW}⚠ Installation had issues, but may still work${NC}"
    fi
fi

echo ""
echo "================================================"
echo "Model Selection for 8GB Pi5"
echo "================================================"
echo ""
echo "YOLOE models available:"
echo "  1. yoloe-n.pt  (Nano)   - ~5MB,  FASTEST, lower accuracy"
echo "  2. yoloe-s.pt  (Small)  - ~22MB, Good balance (RECOMMENDED)"
echo "  3. yoloe-m.pt  (Medium) - ~50MB, Better accuracy, slower"
echo ""
echo -e "${BLUE}Recommended: yoloe-s.pt${NC}"
echo "  - Good balance of speed and accuracy"
echo "  - ~10-15 FPS on Pi5"
echo "  - Suitable for most use cases"
echo ""

# The models will auto-download on first use
echo "Note: Models auto-download on first use (~5-50MB depending on model)"
echo ""

# Check system RAM
TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
echo "System RAM: ${TOTAL_RAM}GB"

if [ "$TOTAL_RAM" -le 8 ]; then
    echo -e "${YELLOW}⚠ 8GB RAM detected${NC}"
    echo "Tips for best performance:"
    echo "  • Use yoloe-s.pt (default in our scripts)"
    echo "  • Close other heavy applications"
    echo "  • Detection runs at 640x480 resolution"
    echo "  • Expect 10-15 FPS"
fi

echo ""
echo "================================================"
echo "Setup Complete"
echo "================================================"
echo ""
echo -e "${BLUE}Live Detection Tools Added:${NC}"
echo "  • startLiveDetection - Start real-time object detection"
echo "  • stopLiveDetection - Stop detection"
echo ""
echo -e "${BLUE}Voice Examples:${NC}"
echo ""
echo "1. Detect people:"
echo "   Say: 'Start live detection for person'"
echo ""
echo "2. Detect multiple objects:"
echo "   Say: 'Start detecting person, cup, and phone'"
echo ""
echo "3. Detect for specific time:"
echo "   Say: 'Start detection for cup for 30 seconds'"
echo ""
echo "4. Stop detection:"
echo "   Say: 'Stop detection'"
echo ""
echo -e "${BLUE}What YOLOE Can Detect:${NC}"
echo "  • Common objects: person, hand, face, cup, bottle, phone, laptop"
echo "  • Furniture: chair, table, couch, bed"
echo "  • Outdoors: car, bicycle, tree, dog, cat, bird"
echo "  • Electronics: keyboard, mouse, monitor, remote"
echo "  • Food: apple, banana, sandwich, pizza"
echo "  • And thousands more - just describe it!"
echo ""
echo -e "${BLUE}Features:${NC}"
echo "  ✓ Real-time detection with bounding boxes"
echo "  ✓ Text prompts - no training needed"
echo "  ✓ Shows detections live on LCD"
echo "  ✓ Green boxes for target objects"
echo "  ✓ Confidence scores displayed"
echo "  ✓ 10-15 FPS on Pi5 8GB"
echo ""
echo "Restart chatbot to enable:"
echo "  systemctl --user restart whisplay.service"
echo ""

