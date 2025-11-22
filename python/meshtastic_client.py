#!/usr/bin/env python3
"""
Meshtastic Client for Whisplay
Allows listing nodes, sending messages, and getting device info.
"""
import sys
import time
import json
import argparse
from pubsub import pub
import meshtastic.serial_interface
from meshtastic import portnums_pb2, mesh_pb2

def get_interface(dev_path=None):
    try:
        # Auto-detect or use specific path
        if dev_path:
            return meshtastic.serial_interface.SerialInterface(dev_path)
        else:
            return meshtastic.serial_interface.SerialInterface()
    except Exception as e:
        print(f"Error connecting to Meshtastic device: {e}", file=sys.stderr)
        return None

def list_nodes(interface):
    """List all nodes in the mesh"""
    nodes = []
    if not interface.nodes:
        return []
    
    for node_id, node in interface.nodes.items():
        user = node.get('user', {})
        metrics = node.get('deviceMetrics', {})
        position = node.get('position', {})
        
        nodes.append({
            "id": node_id,
            "longName": user.get('longName', 'Unknown'),
            "shortName": user.get('shortName', '????'),
            "mac": user.get('macaddr', ''),
            "batteryLevel": metrics.get('batteryLevel', 'N/A'),
            "voltage": metrics.get('voltage', 'N/A'),
            "channelUtil": metrics.get('channelUtilization', 'N/A'),
            "snr": node.get('snr', 'N/A'),
            "lastHeard": node.get('lastHeard', 0),
            "latitude": position.get('latitude'),
            "longitude": position.get('longitude')
        })
    
    # Sort by last heard (most recent first)
    nodes.sort(key=lambda x: x['lastHeard'] or 0, reverse=True)
    return nodes

def send_message(interface, text, dest="^all"):
    """Send a text message"""
    try:
        target_node = None
        
        # Case 1: Explicit Broadcast
        if dest == "^all" or dest.lower() == "broadcast":
            print(f"Sending to BROADCAST: {text}")
            interface.sendText(text)
            return True

        # Case 2: Destination is a Node ID (e.g., !12345678)
        if dest.startswith('!'):
            print(f"Sending to Node ID {dest}: {text}")
            interface.sendText(text, destinationId=dest)
            return True
            
        # Case 3: Search for name (Case-Insensitive)
        dest_lower = dest.lower()
        print(f"Searching for node matching '{dest}'...", file=sys.stderr)
        
        found = False
        for n in interface.nodes.values():
            u = n.get('user', {})
            lName = u.get('longName', '').lower()
            sName = u.get('shortName', '').lower()
            
            if lName == dest_lower or sName == dest_lower:
                target_node = u.get('id')
                name = u.get('longName') or u.get('shortName')
                print(f"Found node '{name}' ({target_node}). Sending direct message.")
                interface.sendText(text, destinationId=target_node)
                found = True
                break
                
        if not found:
            print(f"Warning: Node '{dest}' not found in local mesh DB. Falling back to BROADCAST.", file=sys.stderr)
            # Append intention to text so recipient knows
            # text = f"(@{dest}) {text}" 
            interface.sendText(text) # Broadcast
            
        return True
    except Exception as e:
        print(f"Error sending message: {e}", file=sys.stderr)
        return False

def read_messages(interface, timeout=5):
    """
    Listen for messages for a short duration.
    """
    messages = []
    
    def onReceive(packet, interface):
        try:
            if 'decoded' in packet and packet['decoded'].get('portnum') == 'TEXT_MESSAGE_APP':
                text = packet['decoded'].get('text', '')
                sender = packet.get('fromId', 'Unknown')
                
                # Try to resolve sender name
                sender_info = interface.nodes.get(sender, {}).get('user', {})
                sender_name = sender_info.get('longName', sender_info.get('shortName', sender))
                
                messages.append({
                    "from": sender_name,
                    "fromId": sender,
                    "text": text,
                    "time": time.time()
                })
        except:
            pass

    pub.subscribe(onReceive, "meshtastic.receive.data")
    
    # Wait for messages
    print(f"Listening for {timeout} seconds...", file=sys.stderr)
    time.sleep(timeout)
    
    return messages

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meshtastic Client")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List Nodes
    parser_nodes = subparsers.add_parser("nodes", help="List nodes")
    
    # Send Message
    parser_send = subparsers.add_parser("send", help="Send message")
    parser_send.add_argument("text", help="Message text")
    parser_send.add_argument("--dest", default="^all", help="Destination (shortName or ^all)")
    
    # Read (Listen)
    parser_read = subparsers.add_parser("read", help="Listen for messages")
    parser_read.add_argument("--timeout", type=int, default=10, help="Listen duration in seconds")
    
    # Monitor (Continuous)
    parser_monitor = subparsers.add_parser("monitor", help="Monitor for messages continuously")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    # Connect
    interface = get_interface()
    if not interface:
        sys.exit(1)
        
    try:
        if args.command == "nodes":
            nodes = list_nodes(interface)
            print(json.dumps(nodes, indent=2))
            
        elif args.command == "send":
            success = send_message(interface, args.text, args.dest)
            if success:
                print(json.dumps({"status": "sent", "text": args.text, "dest": args.dest}))
            else:
                sys.exit(1)
                
        elif args.command == "read":
            msgs = read_messages(interface, args.timeout)
            print(json.dumps(msgs, indent=2))
            
        elif args.command == "monitor":
            # Continuous monitoring for piping to stdout
            def onReceive(packet, interface):
                try:
                    # Debug log for ANY packet (verbose)
                    # print(f"DEBUG: Packet received: {packet}", file=sys.stderr)
                    
                    if 'decoded' in packet and packet['decoded'].get('portnum') == 'TEXT_MESSAGE_APP':
                        text = packet['decoded'].get('text', '')
                        sender = packet.get('fromId', 'Unknown')
                        
                        # Try to resolve sender name
                        sender_info = interface.nodes.get(sender, {}).get('user', {})
                        sender_name = sender_info.get('longName', sender_info.get('shortName', sender))
                        
                        msg_data = {
                            "event": "meshtastic_message",
                            "from": sender_name,
                            "text": text,
                            "timestamp": time.time()
                        }
                        print(f"JSON_MSG:{json.dumps(msg_data)}", flush=True)
                except Exception as e:
                    print(f"Error processing packet: {e}", file=sys.stderr)
                    pass

            pub.subscribe(onReceive, "meshtastic.receive.data")
            print("Monitoring for Meshtastic messages...", file=sys.stderr)
            
            while True:
                time.sleep(1)
            
    finally:
        interface.close()
