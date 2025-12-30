#!/usr/bin/env python3
"""
Memory Display - Generates visual representation of Jarvis memory for the Whisplay display

Creates a PNG image showing:
- Memory statistics
- Recent episodes
- Mini knowledge graph visualization

Designed for the 240x240 (or similar) Whisplay LCD screen.
"""

import os
import sys
import json
import socket
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# Add paths
sys.path.insert(0, '/home/dash/optidex/python')

from PIL import Image, ImageDraw, ImageFont
from memory import get_memory

# Output paths
OUTPUT_DIR = Path(os.path.expanduser("~/optidex/data/memory/visualizations"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "memory_display.png"

# Display settings
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 240
BG_COLOR = (15, 15, 25)  # Dark blue-gray
TEXT_COLOR = (200, 220, 255)  # Light blue
ACCENT_COLOR = (100, 180, 255)  # Bright blue
HIGHLIGHT_COLOR = (255, 200, 100)  # Gold
NODE_COLOR = (80, 150, 220)  # Blue
EDGE_COLOR = (60, 100, 140)  # Dark blue

# Try to load a font
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font at the specified size"""
    try:
        path = FONT_BOLD_PATH if bold else FONT_PATH
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()


def create_memory_image(detail_level: str = "summary") -> str:
    """Create a memory visualization image"""
    memory = get_memory()
    stats = memory.get_stats()
    
    # Create image
    img = Image.new('RGB', (DISPLAY_WIDTH, DISPLAY_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(16, bold=True)
    font_normal = get_font(12)
    font_small = get_font(10)
    
    y_pos = 8
    
    # Title
    draw.text((DISPLAY_WIDTH // 2, y_pos), "JARVIS MEMORY", fill=ACCENT_COLOR,
              font=font_title, anchor="mt")
    y_pos += 24
    
    # Divider
    draw.line([(10, y_pos), (DISPLAY_WIDTH - 10, y_pos)], fill=EDGE_COLOR, width=1)
    y_pos += 8
    
    # Stats section - use text-based icons instead of emojis
    items = [
        ("[N]", stats.get("total_nodes", 0) or stats.get("entities", 0) or 0, "Nodes"),
        ("[L]", stats.get("total_edges", 0) or stats.get("relationships", 0) or 0, "Links"),
        ("[E]", stats.get("episodes", 0) or 0, "Episodes"),
        ("[M]", stats.get("active_missions", 0) or 0, "Missions"),
    ]
    
    # Draw stats in 2x2 grid
    col_width = DISPLAY_WIDTH // 2
    for i, (icon, count, label) in enumerate(items):
        x = (i % 2) * col_width + col_width // 2
        y = y_pos + (i // 2) * 35
        
        # Draw icon and count
        draw.text((x, y), icon, fill=ACCENT_COLOR, font=font_normal, anchor="mt")
        draw.text((x, y + 14), str(count), fill=TEXT_COLOR, font=font_title, anchor="mt")
    
    y_pos += 75
    
    # Divider
    draw.line([(10, y_pos), (DISPLAY_WIDTH - 10, y_pos)], fill=EDGE_COLOR, width=1)
    y_pos += 8
    
    # Recent activity section
    draw.text((DISPLAY_WIDTH // 2, y_pos), "RECENT", fill=HIGHLIGHT_COLOR,
              font=font_normal, anchor="mt")
    y_pos += 18
    
    # Get recent episodes
    episodes = memory.get_recent_episodes(limit=3)
    
    if episodes:
        for ep in episodes:
            dt = datetime.fromtimestamp(ep.timestamp)
            time_str = dt.strftime("%H:%M")
            
            # Truncate summary to fit
            summary = ep.summary[:28] + "..." if len(ep.summary) > 28 else ep.summary
            
            # Draw time and summary
            draw.text((10, y_pos), time_str, fill=ACCENT_COLOR, font=font_small)
            draw.text((45, y_pos), summary, fill=TEXT_COLOR, font=font_small)
            y_pos += 14
    else:
        draw.text((DISPLAY_WIDTH // 2, y_pos), "No recent activity", 
                  fill=(100, 100, 100), font=font_small, anchor="mt")
        y_pos += 14
    
    y_pos += 5
    
    # Mini graph visualization if space allows
    if y_pos < DISPLAY_HEIGHT - 60 and detail_level == "graph":
        draw.line([(10, y_pos), (DISPLAY_WIDTH - 10, y_pos)], fill=EDGE_COLOR, width=1)
        y_pos += 5
        
        draw_mini_graph(draw, memory, y_pos)
    
    # Save image
    img.save(OUTPUT_FILE, "PNG")
    return str(OUTPUT_FILE)


def draw_mini_graph(draw: ImageDraw.Draw, memory, start_y: int):
    """Draw a mini representation of the knowledge graph"""
    # Get some nodes to display
    graph = memory.graph if hasattr(memory, 'graph') else None
    if not graph:
        return
    
    # Get a sample of important nodes
    nodes_to_draw = []
    
    # Prioritize: missions, recent entities, concepts
    for node_id, attrs in list(graph.nodes(data=True))[:15]:
        node_type = attrs.get('type', 'unknown')
        if node_type in ['mission', 'entity', 'episode']:
            nodes_to_draw.append((node_id, attrs, node_type))
        if len(nodes_to_draw) >= 6:
            break
    
    if not nodes_to_draw:
        return
    
    # Calculate positions in a circular layout
    import math
    center_x = DISPLAY_WIDTH // 2
    center_y = start_y + 35
    radius = 30
    
    positions = {}
    for i, (node_id, attrs, node_type) in enumerate(nodes_to_draw):
        angle = (2 * math.pi * i) / len(nodes_to_draw) - math.pi / 2
        x = int(center_x + radius * math.cos(angle))
        y = int(center_y + radius * math.sin(angle))
        positions[node_id] = (x, y)
    
    # Draw edges
    for node_id in positions:
        if graph.has_node(node_id):
            for neighbor in list(graph.neighbors(node_id))[:3]:
                if neighbor in positions:
                    draw.line([positions[node_id], positions[neighbor]], 
                             fill=EDGE_COLOR, width=1)
    
    # Draw nodes
    font_tiny = get_font(8)
    for node_id, (x, y) in positions.items():
        attrs = graph.nodes.get(node_id, {})
        node_type = attrs.get('type', 'unknown')
        
        # Color based on type
        if node_type == 'mission':
            color = HIGHLIGHT_COLOR
        elif node_type == 'episode':
            color = (100, 200, 100)  # Green
        else:
            color = NODE_COLOR
        
        # Draw node circle
        draw.ellipse([(x - 6, y - 6), (x + 6, y + 6)], fill=color, outline=TEXT_COLOR)
        
        # Draw label (abbreviated)
        name = attrs.get('name', node_id.split(':')[-1])[:4]
        draw.text((x, y + 12), name, fill=TEXT_COLOR, font=font_tiny, anchor="mt")


def send_to_display(image_path: str, status: str = "Memory", emoji: str = "[M]"):
    """Send the image to the Whisplay display via setLatestGenImg"""
    try:
        # Use the socket to communicate with Node.js server
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect("/tmp/whisplay_command.sock")
        
        # Send command to set the generated image
        message = json.dumps({
            "command": "setLatestGenImg",
            "image": image_path,
            "status": status,
            "emoji": emoji
        }) + "\n"
        
        sock.sendall(message.encode())
        sock.close()
        print(f"[MemoryDisplay] Sent image to display: {image_path}", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"[MemoryDisplay] Error sending to display: {e}", file=sys.stderr)
        
        # Fallback: write to the standard image path that display might be watching
        try:
            import shutil
            fallback_path = "/tmp/whisplay_gen_image.png"
            shutil.copy(image_path, fallback_path)
            print(f"[MemoryDisplay] Copied to fallback path: {fallback_path}", file=sys.stderr)
        except:
            pass
        
        return False


def main():
    parser = argparse.ArgumentParser(description="Jarvis Memory Display")
    parser.add_argument("--detail", choices=["summary", "graph", "full"], default="summary",
                       help="Detail level for visualization")
    parser.add_argument("--display", action="store_true",
                       help="Send to Whisplay display after generating")
    parser.add_argument("--output", "-o", type=str, default=None,
                       help="Custom output path")
    
    args = parser.parse_args()
    
    # Generate image
    image_path = create_memory_image(detail_level=args.detail)
    
    # Copy to custom path if specified
    if args.output:
        import shutil
        shutil.copy(image_path, args.output)
        image_path = args.output
    
    print(f"Generated: {image_path}")
    
    # Send to display if requested
    if args.display:
        send_to_display(image_path)


if __name__ == "__main__":
    main()

