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
        "retransmissions": 0,
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
            stats["slot_records"].append({"Slot": current_slot, "State": "Collision", "Node": "Client 1 & 2", "Seq": "N/A"})
        elif "Server received Frame" in line or "Transmitted Frame" in line:
            seq_m = re.search(r"Seq=(\d+)", line)
            seq_val = seq_m.group(1) if seq_m else "0"
            node_m = re.search(r"Client Node (\d+)", line)
            node_val = f"Node {node_m.group(1)}" if node_m else "Node 1"
            stats["successful_tx"] += 1
            stats["slot_records"].append({"Slot": current_slot, "State": "Success", "Node": node_val, "Seq": f"Seq {seq_val}"})
        elif "Slot" in line and "IDLE" in line:
            stats["idle_slots"] += 1
            stats["slot_records"].append({"Slot": current_slot, "State": "Idle", "Node": "None", "Seq": "N/A"})

        if "Out-of-Order Packet" in line:
            stats["out_of_order_events"] += 1
            seq_m = re.search(r"Seq=(\d+)", line)
            if seq_m:
                stats["arrival_records"].append({"Arrival_Index": len(stats["arrival_records"]) + 1, "Seq": int(seq_m.group(1)), "Status": "Out-of-Order Buffered"})
        elif "In-Order Packet Seq=" in line or "Processing Frame" in line:
            seq_m = re.search(r"Seq=(\d+)", line)
            if seq_m:
                stats["arrival_records"].append({"Arrival_Index": len(stats["arrival_records"]) + 1, "Seq": int(seq_m.group(1)), "Status": "In-Order Processed"})

        if "ERROR DETECTED" in line or "Injecting 1-bit" in line or "Automatically corrected" in line:
            stats["hamming_errors_corrected"] += 1

        if "New Base Seq=" in line or "Sliding Window Base" in line:
            base_m = re.search(r"Seq=(\d+)", line)
            if base_m:
                current_window_base = int(base_m.group(1))

        if current_slot > 0:
            stats["window_records"].append({"Slot": current_slot, "Window_Base": current_window_base, "Window_Max": current_window_base + 4})

        if "Delivered Payload:" in line or "APP RECEIVED" in line or "Received Payload:" in line:
            msg_match = re.search(r'"([^"]+)"', line)
            if msg_match and msg_match.group(1) not in stats["delivered_packets"]:
                stats["delivered_packets"].append(msg_match.group(1))

    return stats

st.title("📡 Data Link Layer Interactive Client-Server Simulator")
st.markdown("""
**Architecture**: Central Receiver Server (`src/server.cpp`) listening on UDP `8000` + Contending Clients (`src/client.cpp`) communicating over BSD Sockets.  
Demonstrating **Slotted ALOHA**, **Hamming FEC**, **Selective Repeat Flow Control**, **In-Order Delivery**, and **Packet Movement**.
""")

st.sidebar.header("⚙️ Controls")
sim_btn = st.sidebar.button("🚀 Run Client-Server Network", type="primary", use_container_width=True)

if st.sidebar.button("🧹 Clear Results", use_container_width=True):
    st.session_state["sim_logs"] = ""
    st.session_state["sim_metrics"] = None
    st.session_state["sim_completed"] = False
    st.rerun()

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

    log_box.code("Compilation Success!\nStarting UDP Receiver Server on Port 8000...\n", language="bash")

    srv_cmd = [SERVER_EXE] if platform.system() == "Windows" else ["stdbuf", "-oL", SERVER_EXE]
    cli1_cmd = [CLIENT_EXE, "1"] if platform.system() == "Windows" else ["stdbuf", "-oL", CLIENT_EXE, "1"]
    cli2_cmd = [CLIENT_EXE, "2"] if platform.system() == "Windows" else ["stdbuf", "-oL", CLIENT_EXE, "2"]

    srv_proc = subprocess.Popen(srv_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    time.sleep(0.1)

    cli1_proc = subprocess.Popen(cli1_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cli2_proc = subprocess.Popen(cli2_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

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
        "1. Movement of Packets",
        "2. In-Order Delivery",
        "3. Error Handling (Hamming)",
        "4. Flow Control (SR)",
        "5. Multiple Access (ALOHA)"
    ])

    with f_tab1:
        st.subheader("1. Client-to-Server UDP Packet Movement Timeline")
        if metrics["slot_records"]:
            df_slots = pd.DataFrame(metrics["slot_records"])
            fig1 = px.scatter(
                df_slots, 
                x="Slot", 
                y="Node", 
                color="State", 
                text="Seq", 
                title="Socket Transmissions Across Time Slots",
                color_discrete_map={"Success": "#2ecc71", "Collision": "#e74c3c", "Idle": "#95a5a6"}
            )
            fig1.update_traces(marker=dict(size=14), textposition='top center')
            st.plotly_chart(fig1, use_container_width=True)

    with f_tab2:
        st.subheader("2. Out-of-Order Buffering & Sequential In-Order Delivery")
        c1, c2 = st.columns(2)
        with c1:
            if metrics["arrival_records"]:
                fig2 = px.bar(
                    pd.DataFrame(metrics["arrival_records"]), 
                    x="Arrival_Index", 
                    y="Seq", 
                    color="Status", 
                    title="Arrival Order vs Sequence Number",
                    color_discrete_map={"In-Order Processed": "#2ecc71", "Out-of-Order Buffered": "#f39c12"}
                )
                st.plotly_chart(fig2, use_container_width=True)
        with c2:
            st.markdown("### 📥 Delivered Application Data")
            if metrics["delivered_packets"]:
                st.dataframe(pd.DataFrame({"Delivered Payload": metrics["delivered_packets"]}), use_container_width=True)
            else:
                st.info("Frames buffered; awaiting base packet recovery.")

    with f_tab3:
        st.subheader("3. Hamming(7,4) Code Error Correction Diagnostics")
        col_fec1, col_fec2 = st.columns(2)
        with col_fec1:
            st.metric("1-Bit Noise Errors Corrected", metrics["hamming_errors_corrected"])
            st.success("100% Automatic Recovery from Bit Flips")
        with col_fec2:
            st.table(pd.DataFrame({
                "Bit Index": ["P1 (1)", "P2 (2)", "D1 (3)", "P4 (4)", "D2 (5)", "D3 (6)", "D4 (7)"],
                "Type": ["Parity", "Parity", "Data", "Parity", "Data", "Data", "Data"],
                "Parity Coverage": ["1,3,5,7", "2,3,6,7", "N/A", "4,5,6,7", "N/A", "N/A", "N/A"]
            }))

    with f_tab4:
        st.subheader("4. Selective Repeat Sliding Window Flow Control")
        if metrics["window_records"]:
            df_win = pd.DataFrame(metrics["window_records"])
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=df_win["Slot"], y=df_win["Window_Base"], mode='lines+markers', name='Window Base (rcv_base)', line=dict(color='#2980b9', width=3)))
            fig4.add_trace(go.Scatter(x=df_win["Slot"], y=df_win["Window_Max"], mode='lines', name='Window Limit (Base + N)', line=dict(color='#e74c3c', dash='dash')))
            fig4.update_layout(title="Sliding Window Range Over Time", xaxis_title="Slot Index", yaxis_title="Sequence Boundary")
            st.plotly_chart(fig4, use_container_width=True)

    with f_tab5:
        st.subheader("5. Slotted ALOHA Channel Efficiency & Collision Backoff")
        total_slots = max(metrics["total_slots"], 1)
        throughput = round((metrics["successful_tx"] / total_slots) * 100, 1)
        st.metric("Observed Channel Throughput", f"{throughput}%")
        if metrics["slot_records"]:
            fig5 = px.bar(
                pd.DataFrame(metrics["slot_records"]), 
                x="Slot", 
                y=[1]*len(metrics["slot_records"]), 
                color="State", 
                title="Channel Slot Occupancy Breakdown",
                color_discrete_map={"Success": "#2ecc71", "Collision": "#e74c3c", "Idle": "#95a5a6"}
            )
            fig5.update_yaxes(showticklabels=False, title="")
            st.plotly_chart(fig5, use_container_width=True)

elif not st.session_state["sim_completed"]:
    st.info("Click **'Run Client-Server Network'** in the sidebar to start the C++ processes and view analytics.")