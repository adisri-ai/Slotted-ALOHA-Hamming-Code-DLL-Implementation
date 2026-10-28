import os
import sys
import time
import platform
import subprocess
import threading
import pyshark
from colorama import Fore, Style, init

init(autoreset=True)

UDP_PORT = 9000
SERVER_CPP = "server.cpp"
CLIENT_CPP = "client.cpp"

SERVER_EXE = "server.exe" if platform.system() == "Windows" else "./server"
CLIENT_EXE = "client.exe" if platform.system() == "Windows" else "./client"


def compile_client_server():
    if not os.path.exists(SERVER_CPP) or not os.path.exists(CLIENT_CPP):
        print(f"{Fore.RED}[ERROR] C++ source files ('{SERVER_CPP}' / '{CLIENT_CPP}') missing.")
        sys.exit(1)

    print(f"{Fore.CYAN}[BUILD] Compiling C++ Client-Server Binaries...")
    
    if platform.system() == "Windows":
        cmd_srv = ["g++", "-std=c++17", SERVER_CPP, "-o", "server.exe", "-lws2_32"]
        cmd_cli = ["g++", "-std=c++17", CLIENT_CPP, "-o", "client.exe", "-lws2_32"]
    else:
        cmd_srv = ["g++", "-std=c++17", SERVER_CPP, "-o", "server"]
        cmd_cli = ["g++", "-std=c++17", CLIENT_CPP, "-o", "client"]

    res_srv = subprocess.run(cmd_srv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res_srv.returncode != 0:
        print(f"{Fore.RED}[BUILD ERROR] Server Compilation Failed:\n{res_srv.stderr}")
        sys.exit(1)

    res_cli = subprocess.run(cmd_cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res_cli.returncode != 0:
        print(f"{Fore.RED}[BUILD ERROR] Client Compilation Failed:\n{res_cli.stderr}")
        sys.exit(1)

    print(f"{Fore.GREEN}[BUILD SUCCESS] Binaries Compiled: '{SERVER_EXE}' and '{CLIENT_EXE}'\n")


def parse_dll_frame(raw_str):
    frame_data = {}
    tokens = raw_str.split('|')
    for token in tokens:
        if ':' in token:
            k, v = token.split(':', 1)
            frame_data[k.strip()] = v.strip()
    return frame_data


def process_pyshark_packet(packet, packet_count):
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

        frame_type = frame.get('TYPE', 'UNKNOWN')
        node_id = frame.get('NODE', '?')
        seq_num = frame.get('SEQ', '?')
        raw_hamming = frame.get('PAYLOAD_HAMMING', '')

        print(f"{Fore.WHITE}Network Layer  : UDP/IP (127.0.0.1:{UDP_PORT})")
        print(f"{Fore.WHITE}Data Link Layer: Node ID = {node_id} | Frame Type = {frame_type}")

        if node_id == '2':
            print(f"{Fore.RED}[MAC - SLOTTED ALOHA] Transmission from Client Node 2 (Collision Contender)")
        else:
            print(f"{Fore.GREEN}[MAC - SLOTTED ALOHA] Transmission from Primary Client Node {node_id}")

        if frame_type == 'DATA':
            print(f"{Fore.MAGENTA}[FLOW CONTROL - SR] DATA Frame Received | Seq No: {seq_num}")
        elif frame_type == 'ACK':
            print(f"{Fore.GREEN}[FLOW CONTROL - SR] Selective ACK Frame Received | ACK No: {seq_num}")

        print(f"{Fore.BLUE}[ERROR CONTROL - HAMMING(7,4)] Payload Hex Stream: {raw_hamming}")
        print(f"{Style.BRIGHT}{Fore.CYAN}{'='*75}\n")

    except Exception:
        pass


def run_pyshark_listener(stop_event):
    iface = r"\Device\NPF_Loopback" if platform.system() == "Windows" else "lo"
    try:
        capture = pyshark.LiveCapture(interface=iface, bpf_filter=f"udp port {UDP_PORT}")
        packet_count = 0
        for packet in capture.sniff_continuously():
            if stop_event.is_set():
                break
            packet_count += 1
            process_pyshark_packet(packet, packet_count)
    except Exception as e:
        print(f"{Fore.RED}[PYSHARK ERROR] {e}")


def main():
    print(f"{Style.BRIGHT}{Fore.MAGENTA}" + "="*75)
    print(f"{Style.BRIGHT}{Fore.MAGENTA}   CLIENT-SERVER DATA LINK LAYER SIMULATOR & PYSHARK MONITOR")
    print(f"{Style.BRIGHT}{Fore.MAGENTA}" + "="*75 + "\n")

    # Step 1: Compile C++ Code
    compile_client_server()

    # Step 2: Launch PyShark Sniffer in background
    stop_pyshark = threading.Event()
    pyshark_thread = threading.Thread(target=run_pyshark_listener, args=(stop_pyshark,), daemon=True)
    pyshark_thread.start()
    time.sleep(1.5)

    # Step 3: Launch C++ Server Process
    print(f"{Fore.CYAN}[SYSTEM] Starting Receiver Server Process on UDP Port 8000...")
    srv_proc = subprocess.Popen([SERVER_EXE], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    time.sleep(1.0)

    # Step 4: Launch Client Node 1 and Client Node 2 Concurrently
    print(f"{Fore.CYAN}[SYSTEM] Launching Client Node 1 and Client Node 2 Concurrently...\n")
    cli1_proc = subprocess.Popen([CLIENT_EXE, "1"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cli2_proc = subprocess.Popen([CLIENT_EXE, "2"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # Stream Server Log Output to Console
    for line in iter(srv_proc.stdout.readline, ''):
        if line:
            print(f"{Fore.YELLOW}[SERVER LOG] {line.strip()}")

    srv_proc.wait()
    cli1_proc.wait()
    cli2_proc.wait()

    time.sleep(1.5)
    stop_pyshark.set()

    print(f"\n{Style.BRIGHT}{Fore.GREEN}" + "="*75)
    print(f"{Style.BRIGHT}{Fore.GREEN}   SIMULATION & CAPTURE COMPLETED")
    print(f"{Style.BRIGHT}{Fore.GREEN}" + "="*75 + "\n")


if __name__ == "__main__":
    main()