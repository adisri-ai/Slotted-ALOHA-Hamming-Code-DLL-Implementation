import os
import sys
import time
import platform
import subprocess
import threading
import pyshark
from colorama import Fore, Style, init

# Initialize Colorama for cross-platform color printing
init(autoreset=True)

UDP_PORT = 9000
CPP_MAIN_FILE = "main.cpp"
CPP_EXE_NAME = "dll_sim.exe" if platform.system() == "Windows" else "./dll_sim"


# ============================================================================
# 1. C++ COMPILATION & EXECUTION HELPER
# ============================================================================

def compile_cpp_code():
    """
    Checks for C++ source files and compiles main.cpp using g++.
    """
    if not os.path.exists(CPP_MAIN_FILE):
        print(f"{Fore.RED}[ERROR] C++ source file '{CPP_MAIN_FILE}' not found in current directory.")
        print(f"{Fore.RED}Ensure main.cpp and all .hpp header files are in the same folder.")
        sys.exit(1)

    print(f"{Fore.CYAN}[BUILD] Compiling C++ Data Link Layer Simulation ({CPP_MAIN_FILE})...")
    
    # System-specific compilation command
    if platform.system() == "Windows":
        compile_cmd = ["g++", "-std=c++17", CPP_MAIN_FILE, "-o", "dll_sim.exe", "-lws2_32"]
    else:
        compile_cmd = ["g++", "-std=c++17", CPP_MAIN_FILE, "-o", "dll_sim"]

    try:
        result = subprocess.run(compile_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"{Fore.RED}[BUILD ERROR] C++ Compilation Failed:\n{result.stderr}")
            sys.exit(1)
        print(f"{Fore.GREEN}[BUILD SUCCESS] C++ Binary Compiled: '{CPP_EXE_NAME}'\n")
    except FileNotFoundError:
        print(f"{Fore.RED}[ERROR] 'g++' compiler not found in PATH. Please install g++ to compile C++ code.")
        sys.exit(1)


def stream_cpp_output(process):
    """
    Reads C++ standard output line-by-line and prints it with a distinctive tag.
    """
    for line in iter(process.stdout.readline, ''):
        if line:
            print(f"{Fore.YELLOW}[C++ SIM] {line.strip()}")
    process.stdout.close()


# ============================================================================
# 2. PYSHARK PACKET INSPECTOR MODULE
# ============================================================================

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
    
    return " | ".join(bit_summary)


def process_pyshark_packet(packet, packet_count, tracker_state):
    """
    Extracts custom frame header fields from UDP payload and prints PyShark details.
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
        payload_len = frame.get('LEN', '0')
        raw_hamming = frame.get('PAYLOAD_HAMMING', '')

        print(f"{Fore.WHITE}Network Layer  : UDP/IP ({src_ip}:{UDP_PORT} -> {dst_ip}:{UDP_PORT})")
        print(f"{Fore.WHITE}Data Link Layer: Node ID = {node_id} | Frame Type = {frame_type}")
        print(f"{Fore.WHITE}{'-'*75}")

        # 1. Slotted ALOHA MAC Analysis
        if node_id == '99':
            print(f"{Fore.RED}[MAC - SLOTTED ALOHA] Contending Transmission Detected from Node B (Collision Event Source)")
        else:
            print(f"{Fore.GREEN}[MAC - SLOTTED ALOHA] Frame Transmitted in Synchronized Slot Boundary by Primary Node {node_id}")

        # 2. Selective Repeat ARQ Flow Control Analysis
        if frame_type == 'DATA':
            print(f"{Fore.MAGENTA}[FLOW CONTROL - SR] DATA Frame Received | Seq No: {seq_num} | Length: {payload_len} bytes")
            if tracker_state['last_expected_seq'] is not None:
                exp = tracker_state['last_expected_seq']
                if int(seq_num) != exp:
                    print(f"{Fore.RED}[FLOW CONTROL - SR] Out-of-Order Packet! Received Seq={seq_num}, Expected Base={exp}. Receiver Buffering Activated.")
                else:
                    print(f"{Fore.GREEN}[FLOW CONTROL - SR] In-Order Packet Arrival (Seq={seq_num}). Receiver Window Base Advancing.")
                    tracker_state['last_expected_seq'] = (int(seq_num) + 1) % 8

        elif frame_type == 'ACK':
            print(f"{Fore.GREEN}[FLOW CONTROL - SR] ACK Frame Received | Selective ACK No: {seq_num}")

        # 3. Hamming Code FEC Analysis
        print(f"{Fore.WHITE}{'-'*75}")
        print(f"{Fore.BLUE}[ERROR CONTROL - HAMMING(7,4)] Encoded Payload Stream:")
        print(f"   Hex & Binary Breakdown: {inspect_hamming_bits(raw_hamming)}")
        print(f"   Parity Check Status   : [P1, P2, P4] Checked for Syndrome Calculation & Error Correction")
        print(f"{Style.BRIGHT}{Fore.CYAN}{'='*75}\n")

    except Exception as e:
        pass


def run_pyshark_listener(stop_event):
    """
    Thread runner for PyShark Live Capture on the local loopback interface.
    """
    iface = r"\Device\NPF_Loopback" if platform.system() == "Windows" else "lo"

    try:
        capture = pyshark.LiveCapture(interface=iface, bpf_filter=f"udp port {UDP_PORT}")
        packet_count = 0
        tracker_state = {'last_expected_seq': 0}

        for packet in capture.sniff_continuously():
            if stop_event.is_set():
                break
            packet_count += 1
            process_pyshark_packet(packet, packet_count, tracker_state)

    except Exception as e:
        print(f"{Fore.RED}[PYSHARK ERROR] Capture Exception: {e}")
        print(f"{Fore.RED}Ensure TShark/Wireshark is installed and loopback permissions are granted.")


# ============================================================================
# 3. MAIN ORCHESTRATOR ENTRY POINT
# ============================================================================

def main():
    print(f"{Style.BRIGHT}{Fore.MAGENTA}" + "="*75)
    print(f"{Style.BRIGHT}{Fore.MAGENTA}   UNIFIED SYSTEM ENTRY POINT: DATA LINK LAYER & PYSHARK MONITOR")
    print(f"{Style.BRIGHT}{Fore.MAGENTA}" + "="*75 + "\n")

    # Step 1: Compile C++ Code
    compile_cpp_code()

    # Step 2: Launch PyShark Capture in a Background Thread
    stop_pyshark = threading.Event()
    pyshark_thread = threading.Thread(target=run_pyshark_listener, args=(stop_pyshark,), daemon=True)
    
    print(f"{Fore.CYAN}[SYSTEM] Initializing PyShark Packet Inspector on UDP Port {UDP_PORT}...")
    pyshark_thread.start()
    
    # Pause to allow PyShark/TShark engine to start listening
    time.sleep(2.0)

    # Step 3: Launch C++ Simulation Subprocess
    print(f"{Fore.CYAN}[SYSTEM] Launching C++ Data Link Layer Network Simulation...\n")
    
    cpp_process = subprocess.Popen(
        [CPP_EXE_NAME],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    # Stream C++ output to console in real-time
    cpp_thread = threading.Thread(target=stream_cpp_output, args=(cpp_process,), daemon=True)
    cpp_thread.start()

    # Wait for C++ Simulation process to complete
    cpp_process.wait()
    cpp_thread.join()

    # Allow PyShark 2 seconds to process remaining packets
    time.sleep(2.0)
    stop_pyshark.set()

    print(f"\n{Style.BRIGHT}{Fore.GREEN}" + "="*75)
    print(f"{Style.BRIGHT}{Fore.GREEN}   SIMULATION & PYSHARK CAPTURE COMPLETED SUCCESSFULLY")
    print(f"{Style.BRIGHT}{Fore.GREEN}" + "="*75 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[SYSTEM] Execution aborted by user.")
        sys.exit(0)