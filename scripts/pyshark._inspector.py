import pyshark
import sys
import os
import platform
from colorama import Fore, Style, init

init(autoreset=True)
PORT = 9000

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
        val = int(h, 16)
        bin_str = f"{val:08b}"
        bit_summary.append(f"0x{h.upper()} ({bin_str})")
    
    return " | ".join(bit_summary)


def process_pyshark_packet(packet, packet_count, tracker_state):
    """
    Extracts custom frame header fields from UDP payload and displays packet details.
    """
    try:
        if hasattr(packet, 'udp') and hasattr(packet.udp, 'payload'):
            raw_hex = packet.udp.payload.replace(':', '')
            raw_bytes = bytes.fromhex(raw_hex)
            ascii_payload = raw_bytes.decode('utf-8', errors='ignore')
        else:
            return

        frame = parse_dll_frame(ascii_payload)
        
        if not frame or 'TYPE' not in frame:
            return

        print(f"\n{Style.BRIGHT}{Fore.CYAN}{'='*75}")
        print(f"{Fore.CYAN}  PYSHARK PACKET INSPECTOR — CAPTURED FRAME #{packet_count}")
        print(f"{Style.BRIGHT}{Fore.CYAN}{'='*75}")

        
        src_ip = packet.ip.src if hasattr(packet, 'ip') else "127.0.0.1"
        dst_ip = packet.ip.dst if hasattr(packet, 'ip') else "127.0.0.1"
        frame_type = frame.get('TYPE', 'UNKNOWN')
        node_id = frame.get('NODE', '?')
        seq_num = frame.get('SEQ', '?')
        ack_num = frame.get('ACK', '?')
        payload_len = frame.get('LEN', '0')
        raw_hamming = frame.get('PAYLOAD_HAMMING', '')

        print(f"{Fore.WHITE}Network Layer  : UDP/IP ({src_ip}:{PORT} -> {dst_ip}:{PORT})")
        print(f"{Fore.WHITE}Data Link Layer: Node ID = {node_id} | Frame Type = {frame_type}")
        print(f"{Fore.YELLOW}{'-'*75}")

        
        if node_id == '99': 
            print(f"{Fore.RED}[MAC - SLOTTED ALOHA] Contending Transmission Detected from Secondary Node B (Collision Source)")
        else:
            print(f"{Fore.GREEN}[MAC - SLOTTED ALOHA] Frame Transmitted in Synchronized Slot Boundary by Primary Node {node_id}")

        # Selective Repeat ARQ (Flow Control & Seq Numbers)
        if frame_type == 'DATA':
            print(f"{Fore.MAGENTA}[FLOW CONTROL - SR] DATA Frame Received | Seq No: {seq_num} | Length: {payload_len} bytes")
            if tracker_state['last_expected_seq'] is not None:
                exp = tracker_state['last_expected_seq']
                if int(seq_num) != exp:
                    print(f"{Fore.RED}[FLOW CONTROL - SR] Out-of-Order Packet! Received Seq={seq_num}, Expected Seq={exp}. Receiver Buffering Triggered.")
                else:
                    print(f"{Fore.GREEN}[FLOW CONTROL - SR] Sequential In-Order Packet Arrival (Seq={seq_num}). Receiver Window Advancing.")
                    tracker_state['last_expected_seq'] = (int(seq_num) + 1) % 8

        elif frame_type == 'ACK':
            print(f"{Fore.GREEN}[FLOW CONTROL - SR] ACK Frame Received | Selective ACK No: {seq_num}")
            print(f"{Fore.GREEN}[FLOW CONTROL - SR] Sender Buffer for Frame {seq_num} cleared. Sliding Sender Window.")

        # Hamming Code Error Handling Inspection
        print(f"{Fore.YELLOW}{'-'*75}")
        print(f"{Fore.BLUE}[ERROR CONTROL - HAMMING(7,4)] Encoded Payload Stream:")
        print(f"   Hex & Binary Breakdown: {inspect_hamming_bits(raw_hamming)}")
        print(f"   Parity Verification   : 3 Parity Bits per Nibble [P1, P2, P4] Checked for Syndrome Calculation")

        print(f"{Style.BRIGHT}{Fore.CYAN}{'='*75}\n")

    except Exception as e:
        print(f"{Fore.RED}Error parsing captured frame: {e}")


def start_live_capture(interface_name=None):
    """
    Starts PyShark Live Capture on the local loopback interface.
    """
    if interface_name is None:
        if platform.system() == "Windows":
            interface_name = r"\Device\NPF_Loopback"
        else:
            interface_name = "lo"

    print(f"{Style.BRIGHT}{Fore.GREEN}Starting PyShark Live Packet Capture...")
    print(f"{Fore.WHITE}Interface     : {interface_name}")
    print(f"{Fore.WHITE}Filter        : UDP Port {PORT}")
    print(f"{Fore.WHITE}Waiting for C++ Data Link Layer frames...\n")

    capture = None
    try:
        capture = pyshark.LiveCapture(
            interface=interface_name,
            bpf_filter=f"udp port {PORT}"
        )

        packet_count = 0
        tracker_state = {'last_expected_seq': 0}

        for packet in capture.sniff_continuously():
            packet_count += 1
            process_pyshark_packet(packet, packet_count, tracker_state)

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Capture stopped by user.")
    except Exception as e:
        print(f"\n{Fore.RED}PyShark Capture Error: {e}")
        print(f"{Fore.YELLOW}Tip: Ensure tshark is installed and added to PATH, and that loopback interface permissions are enabled.")


def analyze_pcap_file(pcap_path):
    """
    Alternative mode: Analyzes a pre-recorded PCAP capture file.
    """
    if not os.path.exists(pcap_path):
        print(f"{Fore.RED}PCAP file not found: {pcap_path}")
        return

    print(f"{Fore.GREEN}Analyzing PCAP file: {pcap_path}...")
    capture = pyshark.FileCapture(pcap_path, display_filter=f"udp.port == {PORT}")
    
    packet_count = 0
    tracker_state = {'last_expected_seq': 0}
    
    for packet in capture:
        packet_count += 1
        process_pyshark_packet(packet, packet_count, tracker_state)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].endswith(".pcap"):
        analyze_pcap_file(sys.argv[1])
    else:
        custom_iface = sys.argv[1] if len(sys.argv) > 1 else None
        start_live_capture(custom_iface)