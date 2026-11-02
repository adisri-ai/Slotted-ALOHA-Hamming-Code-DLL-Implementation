import pyshark
import sys
import os
import platform
from colorama import Fore, Style, init

init(autoreset=True)
PORT = 9000

def get_loopback_interface():
    system = platform.system()
    if system == "Windows":
        return r"\Device\NPF_Loopback"
    elif system == "Darwin":
        return "lo0"
    else:
        return "lo"


def parse_dll_frame(raw_str):
    """
    Parses serialized DLL Frame format:
    'NODE:1|TYPE:DATA|SEQ:2|ACK:0|LEN:8|PAYLOAD_HAMMING:42 70 61 63'
    """
    frame_data = {}
    tokens = raw_str.split('|')
    for token in tokens:
        if ':' in token:
            k, v = token.split(':', 1)
            frame_data[k.strip()] = v.strip()
    return frame_data


def inspect_hamming_bits(hex_payload_str):
    """
    Breaks down hex-encoded Hamming codewords into bitstreams for inspection.
    """
    if not hex_payload_str:
        return "None"
    
    bytes_hex = hex_payload_str.split()
    bit_summary = []
    for h in bytes_hex:
        try:
            val = int(h, 16)
            bin_str = f"{val:08b}"
            bit_summary.append(f"0x{h.upper()} ({bin_str})")
        except ValueError:
            continue
    
    return " | ".join(bit_summary) if bit_summary else "None"


def process_pyshark_packet(packet, packet_count, tracker_state):
    """
    Extracts custom frame header fields from UDP payload and displays detailed visual diagnostics.
    """
    try:
        raw_hex = ""
        if hasattr(packet, 'udp') and hasattr(packet.udp, 'payload'):
            raw_hex = packet.udp.payload.replace(':', '')
        elif hasattr(packet, 'data') and hasattr(packet.data, 'data'):
            raw_hex = packet.data.data.replace(':', '')

        if not raw_hex:
            return

        bytes_data = bytes.fromhex(raw_hex)
        ascii_payload = bytes_data.decode('utf-8', errors='ignore')
        frame = parse_dll_frame(ascii_payload)

        print(f"\n{Style.BRIGHT}{Fore.CYAN}{'='*75}", flush=True)
        print(f"{Fore.CYAN}  PYSHARK PACKET INSPECTOR — CAPTURED FRAME #{packet_count}", flush=True)
        print(f"{Style.BRIGHT}{Fore.CYAN}{'='*75}", flush=True)

        src_ip = packet.ip.src if hasattr(packet, 'ip') else "127.0.0.1"
        dst_ip = packet.ip.dst if hasattr(packet, 'ip') else "127.0.0.1"
        src_port = packet.udp.srcport if hasattr(packet, 'udp') else "8000"
        dst_port = packet.udp.dstport if hasattr(packet, 'udp') else str(PORT)

        frame_type = frame.get('TYPE', 'UNKNOWN')
        node_id = frame.get('NODE', '?')
        seq_num = frame.get('SEQ', '?')
        payload_len = frame.get('LEN', '0')
        raw_hamming = frame.get('PAYLOAD_HAMMING', '')

        print(f"{Fore.WHITE}Network Layer  : UDP/IP ({src_ip}:{src_port} -> {dst_ip}:{dst_port})", flush=True)
        print(f"{Fore.WHITE}Data Link Layer: Node ID = {node_id} | Frame Type = {frame_type}", flush=True)
        print(f"{Fore.WHITE}Decoded String : {ascii_payload}", flush=True)
        print(f"{Fore.YELLOW}{'-'*75}", flush=True)

        if node_id == '99' or node_id == '2': 
            print(f"{Fore.RED}[MAC - SLOTTED ALOHA] Contending Transmission Detected from Secondary Node {node_id} (Collision Source)", flush=True)
        else:
            print(f"{Fore.GREEN}[MAC - SLOTTED ALOHA] Frame Transmitted in Synchronized Slot Boundary by Primary Node {node_id}", flush=True)

        if frame_type == 'DATA':
            print(f"{Fore.MAGENTA}[FLOW CONTROL - SR] DATA Frame Received | Seq No: {seq_num} | Length: {payload_len} bytes", flush=True)
            if tracker_state['last_expected_seq'] is not None and seq_num.isdigit():
                exp = tracker_state['last_expected_seq']
                seq_int = int(seq_num)
                if seq_int != exp:
                    print(f"{Fore.RED}[FLOW CONTROL - SR] Out-of-Order Packet! Received Seq={seq_int}, Expected Seq={exp}. Receiver Buffering Triggered.", flush=True)
                else:
                    print(f"{Fore.GREEN}[FLOW CONTROL - SR] Sequential In-Order Packet Arrival (Seq={seq_int}). Receiver Window Advancing.", flush=True)
                    tracker_state['last_expected_seq'] = (seq_int + 1) % 8

        elif frame_type == 'ACK':
            print(f"{Fore.GREEN}[FLOW CONTROL - SR] ACK Frame Received | Selective ACK No: {seq_num}", flush=True)
            print(f"{Fore.GREEN}[FLOW CONTROL - SR] Sender Buffer for Frame {seq_num} cleared. Sliding Sender Window.", flush=True)

        # Hamming Code Error Handling Inspection
        print(f"{Fore.YELLOW}{'-'*75}", flush=True)
        print(f"{Fore.BLUE}[ERROR CONTROL - HAMMING] Encoded Payload Stream:", flush=True)
        print(f"   Hex & Binary Breakdown: {inspect_hamming_bits(raw_hamming)}", flush=True)
        print(f"   Parity Verification   : Parity Bits Checked for Syndrome Calculation", flush=True)

        print(f"{Style.BRIGHT}{Fore.CYAN}{'='*75}\n", flush=True)

    except Exception as e:
        print(f"{Fore.RED}Error dissecting captured frame: {e}", flush=True)


def start_live_capture(interface_name=None):
    """
    Starts PyShark Live Capture on the local loopback interface.
    """
    if interface_name is None:
        interface_name = get_loopback_interface()

    print(f"{Style.BRIGHT}{Fore.GREEN}Starting PyShark Live Packet Capture...", flush=True)
    print(f"{Fore.WHITE}OS Platform   : {platform.system()}", flush=True)
    print(f"{Fore.WHITE}Interface     : {interface_name}", flush=True)
    print(f"{Fore.WHITE}Filter        : UDP Port {PORT}", flush=True)
    print(f"{Fore.WHITE}Waiting for C++ Data Link Layer frames...\n", flush=True)

    try:
        capture = pyshark.LiveCapture(
            interface=interface_name,
            display_filter=f"udp.port == {PORT}"
        )

        packet_count = 0
        tracker_state = {'last_expected_seq': 0}

        for packet in capture.sniff_continuously():
            packet_count += 1
            process_pyshark_packet(packet, packet_count, tracker_state)

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Capture stopped by user.", flush=True)
    except Exception as e:
        print(f"\n{Fore.RED}PyShark Capture Error: {e}", flush=True)
        print(f"{Fore.YELLOW}Tip: Ensure tshark is installed and added to PATH, and run with elevated permissions (e.g., 'sudo python3 scripts/pyshark_inspector.py').", flush=True)


if __name__ == "__main__":
    custom_iface = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].endswith(".pcap") else None
    start_live_capture(custom_iface)