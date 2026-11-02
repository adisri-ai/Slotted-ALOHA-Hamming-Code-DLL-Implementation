import os
import sys
import time
import platform
import subprocess
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Data Link Layer Client-Server Simulation",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

SERVER_CPP = os.path.join("src", "server.cpp")
CLIENT_CPP = os.path.join("src", "client.cpp")
BUILD_DIR = "build"

SERVER_EXE = os.path.join(BUILD_DIR, "server.exe") if platform.system() == "Windows" else f"./{BUILD_DIR}/server"
CLIENT_EXE = os.path.join(BUILD_DIR, "client.exe") if platform.system() == "Windows" else f"./{BUILD_DIR}/client"

if "sim_logs" not in st.session_state:
    st.session_state["sim_logs"] = ""
if "sim_metrics" not in st.session_state:
    st.session_state["sim_metrics"] = None
if "sim_completed" not in st.session_state:
    st.session_state["sim_completed"] = False


def compile_client_server():
    os.makedirs(BUILD_DIR, exist_ok=True)

    if not os.path.exists(SERVER_CPP) or not os.path.exists(CLIENT_CPP):
        return False, f"Source files '{SERVER_CPP}' or '{CLIENT_CPP}' missing."

    if platform.system() == "Windows":
        cmd_srv = ["g++", "-std=c++17", "-Iinclude", SERVER_CPP, "-o", SERVER_EXE, "-lws2_32"]
        cmd_cli = ["g++", "-std=c++17", "-Iinclude", CLIENT_CPP, "-o", CLIENT_EXE, "-lws2_32"]
    else:
        cmd_srv = ["g++", "-std=c++17", "-Iinclude", SERVER_CPP, "-o", SERVER_EXE]
        cmd_cli = ["g++", "-std=c++17", "-Iinclude", CLIENT_CPP, "-o", CLIENT_EXE]

    res1 = subprocess.run(cmd_srv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res1.returncode != 0:
        return False, f"Server Compilation Error:\n{res1.stderr}"

    res2 = subprocess.run(cmd_cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res2.returncode != 0:
        return False, f"Client Compilation Error:\n{res2.stderr}"

    return True, "Client & Server Compiled Successfully!"


def parse_simulation_output(raw_logs):
    stats = {
        "total_slots": 0,
        "collisions": 0,
        "successful_tx": 0,
        "idle_slots": 0,
        "hamming_errors_corrected": 0,
        "out_of_order_events": 0,
        "delivered_packets": [],
        "slot_records": [],
        "window_records": [],
        "arrival_records": []
    }

    slot_re = re.compile(r"===\s*TIME SLOT\s*(\d+)\s*===")
    current_slot = 0
    current_window_base = 0

    for line in raw_logs.splitlines():
        slot_match = slot_re.search(line)
        if slot_match:
            current_slot = int(slot_match.group(1))
            stats["total_slots"] = max(stats["total_slots"], current_slot)

        if "COLLISION DETECTED" in line:
            stats["collisions"] += 1
            stats["slot_records"].append({"Slot": current_slot, "State": "Collision", "Node": "Clients 1 & 2", "Seq": "N/A"})
        elif "Server received Frame" in line or "Transmitted Frame" in line:
            seq_m = re.search(r"Seq=(\d+)", line)
            node_m = re.search(r"Client Node (\d+)", line)
            stats["successful_tx"] += 1
            stats["slot_records"].append({
                "Slot": current_slot, 
                "State": "Success", 
                "Node": f"Node {node_m.group(1)}" if node_m else "Node 1", 
                "Seq": f"Seq {seq_m.group(1)}" if seq_m else "Seq 0"
            })
        elif "Slot" in line and "IDLE" in line:
            stats["idle_slots"] += 1
            stats["slot_records"].append({"Slot": current_slot, "State": "Idle", "Node": "None", "Seq": "N/A"})

        if "Out-of-Order Packet" in line:
            stats["out_of_order_events"] += 1
            seq_m = re.search(r"Seq=(\d+)", line)
            if seq_m:
                stats["arrival_records"].append({"Arrival_Index": len(stats["arrival_records"]) + 1, "Seq": int(seq_m.group(1)), "Status": "Out-of-Order Buffered"})
        elif "In-Order Delivery" in line or "Processing Frame" in line:
            seq_m = re.search(r"(?:Seq=|Packet-)(\d+)", line)
            if seq_m:
                stats["arrival_records"].append({"Arrival_Index": len(stats["arrival_records"]) + 1, "Seq": int(seq_m.group(1)), "Status": "In-Order Processed"})

        if any(k in line for k in ["HAMMING FEC", "Automatically corrected", "Injecting", "1-bit noise", "Single-bit error"]):
            stats["hamming_errors_corrected"] += 1

        base_m = re.search(r"(?:Base=|Window Base advanced to Base=)(\d+)", line)
        if base_m:
            current_window_base = int(base_m.group(1))

        if current_slot > 0:
            stats["window_records"].append({
                "Slot": current_slot,
                "Window_Base": current_window_base,
                "Window_Max": current_window_base + 4
            })

        if "Delivered Payload:" in line or "App Received:" in line:
            msg_match = re.search(r'"([^"]+)"', line)
            if msg_match and msg_match.group(1) not in stats["delivered_packets"]:
                stats["delivered_packets"].append(msg_match.group(1))

    return stats


st.sidebar.header("⚙️ Dynamic Parameters")
timeout_ms = st.sidebar.number_input("1. Retransmission Timeout (ms)", min_value=200, max_value=5000, value=1000, step=100)
hamming_n = st.sidebar.number_input("2. Hamming Codeword Length (n)", min_value=7, max_value=31, value=7, step=1)
hamming_k = st.sidebar.number_input("3. Hamming Data Bits (k)", min_value=4, max_value=26, value=4, step=1)

sim_btn = st.sidebar.button("🚀 Run Client-Server Network", type="primary", use_container_width=True)

if st.sidebar.button("🧹 Clear Results", use_container_width=True):
    st.session_state["sim_logs"] = ""
    st.session_state["sim_metrics"] = None
    st.session_state["sim_completed"] = False
    st.rerun()

st.title("📡 Data Link Layer Interactive Client-Server Simulator")
st.markdown("""
**Architecture**: Receiver Server (`src/server.cpp`) listening on UDP `8000` + Contending Clients (`src/client.cpp`).  
Demonstrating **Slotted ALOHA**, **Hamming FEC**, **Selective Repeat ARQ**, and **In-Order Delivery**.
""")

log_container = st.expander("📄 Real-Time Server & Channel Logs", expanded=True)
log_box = log_container.empty()

if sim_btn:
    st.session_state["sim_logs"] = ""
    st.session_state["sim_completed"] = False

    log_box.code("Compiling C++ Client and Server binaries...", language="bash")
    ok, msg = compile_client_server()
    if not ok:
        st.error(msg)
        st.stop()

    log_box.code("Compilation Success!\nStarting Server and Client Processes...\n", language="bash")

    srv_args = [SERVER_EXE, str(timeout_ms), str(hamming_n), str(hamming_k)]
    cli1_args = [CLIENT_EXE, "1", str(timeout_ms), str(hamming_n), str(hamming_k)]
    cli2_args = [CLIENT_EXE, "2", str(timeout_ms), str(hamming_n), str(hamming_k)]

    if platform.system() != "Windows":
        srv_args = ["stdbuf", "-oL"] + srv_args
        cli1_args = ["stdbuf", "-oL"] + cli1_args
        cli2_args = ["stdbuf", "-oL"] + cli2_args

    srv_proc = subprocess.Popen(srv_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    time.sleep(0.1)

    cli1_proc = subprocess.Popen(cli1_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cli2_proc = subprocess.Popen(cli2_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    accumulated = ""
    while True:
        line = srv_proc.stdout.readline()
        if not line and srv_proc.poll() is not None:
            break
        if line:
            accumulated += line
            log_box.code(accumulated, language="text")

    srv_proc.wait()
    cli1_proc.wait()
    cli2_proc.wait()

    st.session_state["sim_logs"] = accumulated
    st.session_state["sim_metrics"] = parse_simulation_output(accumulated)
    st.session_state["sim_completed"] = True

if st.session_state["sim_logs"]:
    log_box.code(st.session_state["sim_logs"], language="text")

if st.session_state["sim_completed"] and st.session_state["sim_metrics"]:
    metrics = st.session_state["sim_metrics"]
    st.markdown("---")
    st.header("🎯 Feature Visual Analytics & Protocol Diagnostics")

    f_tab1, f_tab2, f_tab3, f_tab4, f_tab5 = st.tabs([
        "🚀 1. Movement of Packets",
        "📦 2. In-Order Delivery",
        "🛡️ 3. Error Handling (Hamming)",
        "🔄 4. Flow Control (SR)",
        "⚡ 5. Multiple Access (ALOHA)"
    ])

    with f_tab1:
        st.subheader("1. Socket Transmissions Timeline")
        if metrics["slot_records"]:
            df_slots = pd.DataFrame(metrics["slot_records"])
            fig1 = px.scatter(
                df_slots, x="Slot", y="Node", color="State", text="Seq",
                title="Socket Transmissions Across Time Slots",
                color_discrete_map={"Success": "#2ecc71", "Collision": "#e74c3c", "Idle": "#95a5a6"}
            )
            fig1.update_traces(marker=dict(size=14), textposition='top center')
            st.plotly_chart(fig1, use_container_width=True)

    with f_tab2:
        st.subheader("2. Out-of-Order Buffering & Sequential Delivery")
        c1, c2 = st.columns(2)
        with c1:
            if metrics["arrival_records"]:
                fig2 = px.bar(
                    pd.DataFrame(metrics["arrival_records"]), x="Arrival_Index", y="Seq", color="Status",
                    title="Arrival Order vs Sequence Number",
                    color_discrete_map={"In-Order Processed": "#2ecc71", "Out-of-Order Buffered": "#f39c12"}
                )
                st.plotly_chart(fig2, use_container_width=True)
        with c2:
            st.markdown("### 📥 Delivered Application Data")
            if metrics["delivered_packets"]:
                st.dataframe(pd.DataFrame({"Delivered Payload": metrics["delivered_packets"]}), use_container_width=True)

    with f_tab3:
        st.subheader("3. Hamming Code FEC Error Handling Diagnostics")
        col_fec1, col_fec2 = st.columns(2)
        with col_fec1:
            st.metric("1-Bit Noise Errors Corrected", metrics["hamming_errors_corrected"])
            st.metric("Configured Code Block", f"({hamming_n}, {hamming_k})")
            
            # Plotly bar chart comparing total processed frames vs corrected error frames
            df_fec = pd.DataFrame({
                "Category": ["Clean Frames Received", "Bit-Errors Corrected"],
                "Count": [max(metrics["successful_tx"] - metrics["hamming_errors_corrected"], 0), metrics["hamming_errors_corrected"]]
            })
            fig3 = px.bar(
                df_fec, x="Category", y="Count", color="Category",
                title="Forward Error Correction (FEC) Impact",
                color_discrete_map={"Clean Frames Received": "#2ecc71", "Bit-Errors Corrected": "#e67e22"}
            )
            st.plotly_chart(fig3, use_container_width=True)

        with col_fec2:
            st.markdown("### 🧬 Codeword Bit Matrix")
            st.table(pd.DataFrame({
                "Bit Index": ["P1 (1)", "P2 (2)", "D1 (3)", "P4 (4)", "D2 (5)", "D3 (6)", "D4 (7)"],
                "Type": ["Parity", "Parity", "Data", "Parity", "Data", "Data", "Data"],
                "Parity Coverage": ["1,3,5,7", "2,3,6,7", "N/A", "4,5,6,7", "N/A", "N/A", "N/A"]
            }))

    with f_tab4:
        st.subheader("4. Selective Repeat Sliding Window Flow Control")
        if metrics["window_records"]:
            df_win = pd.DataFrame(metrics["window_records"]).drop_duplicates(subset=["Slot"])
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=df_win["Slot"], y=df_win["Window_Base"], mode='lines+markers', name='Window Base'))
            fig4.add_trace(go.Scatter(x=df_win["Slot"], y=df_win["Window_Max"], mode='lines', name='Window Limit', line=dict(dash='dash')))
            st.plotly_chart(fig4, use_container_width=True)

    with f_tab5:
        st.subheader("5. Slotted ALOHA Channel Efficiency & Multiple Access")
        total_slots = max(metrics["total_slots"], 1)
        throughput = round((metrics["successful_tx"] / total_slots) * 100, 1)

        m1, m2, m3 = st.columns(3)
        m1.metric("Observed Channel Throughput", f"{throughput}%")
        m2.metric("Collisions Detected", metrics["collisions"])
        m3.metric("Idle Slots", metrics["idle_slots"])

        if metrics["slot_records"]:
            df_slots = pd.DataFrame(metrics["slot_records"])
            fig5 = px.bar(
                df_slots,
                x="Slot",
                y=[1] * len(df_slots),
                color="State",
                title="Channel Slot Occupancy Breakdown Across Time Slots",
                color_discrete_map={"Success": "#2ecc71", "Collision": "#e74c3c", "Idle": "#95a5a6"}
            )
            fig5.update_yaxes(showticklabels=False, title="")
            st.plotly_chart(fig5, use_container_width=True)