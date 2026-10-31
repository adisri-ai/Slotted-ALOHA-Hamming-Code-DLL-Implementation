#include <iostream>
#include <vector>
#include <string>
#include <thread>
#include <chrono>

#include "HammingCode.hpp"
#include "Frame.hpp"
#include "SelectiveRepeat.hpp"
#include "SlottedALOHA.hpp"
#include "Channel.hpp"
using namespace std;
int main() {
    cout << "  DATA LINK LAYER SIMULATION ENGINE (SLOTTED ALOHA, HAMMING, SELECTIVE REPEAT)\n";

    ChannelSimulator channel;
    SelectiveRepeatSender sender(4, 8);
    SelectiveRepeatReceiver receiver(4, 8);

    Node nodeA(1); // Primary Sender
    Node nodeB(2); // Secondary Sender (forces Slotted ALOHA collision)

    vector<string> messages = {"Packet-0", "Packet-1", "Packet-2", "Packet-3"};

    // FEATURE 4: FLOW CONTROL (INITIALIZING SENDER SLIDING WINDOW)
    cout << "[FEATURE 4: FLOW CONTROL] Initializing Sender Sliding Window (Window Size = 4)...\n";
    for (const auto& msg : messages) {
        vector<uint8_t> raw_bytes(msg.begin(), msg.end());
        sender.sendPacket(nodeA.node_id, raw_bytes);
    }

    for (auto& pair : sender.window_buffer) {
        nodeA.tx_queue.push(pair.second.frame);
    }

    Frame collision_frame;
    collision_frame.node_id = nodeB.node_id;
    collision_frame.type = FRAME_DATA;
    collision_frame.seq_num = 99;
    collision_frame.encoded_payload = HammingCode::encodeBuffer({'C', 'L'});
    nodeB.tx_queue.push(collision_frame);

    int current_slot = 1;
    bool force_noise_once = true;
    bool simulate_packet_drop = true;

    while (!nodeA.tx_queue.empty() || !nodeB.tx_queue.empty() || !sender.window_buffer.empty()) {
        cout << "=== TIME SLOT " << current_slot << " ===\n";

        // FEATURE 5: MULTIPLE ACCESS (SLOTTED ALOHA SLOT BOUNDARY CHECK)
        bool nodeA_wants = nodeA.canTransmitInSlot();
        bool nodeB_wants = nodeB.canTransmitInSlot();

        if (nodeA_wants && nodeB_wants) {
            cout << "[FEATURE 5: MULTIPLE ACCESS] COLLISION DETECTED in Slot " << current_slot 
                      << "! Both Node 1 and Node 2 transmitted simultaneously.\n";
            nodeA.handleCollision();
            nodeB.handleCollision();
        } 
        else if (nodeA_wants) {
            Frame tx_frame = nodeA.tx_queue.front();

            if (tx_frame.seq_num == 1 && simulate_packet_drop) {
                // Simulate frame drop
                cout << "[FEATURE 1: MOVEMENT OF PACKETS] Frame Seq=1 was LOST in transit over the physical channel!\n";
                nodeA.handleSuccess();
                simulate_packet_drop = false;
            } 
            else {
                // FEATURE 3: ERROR HANDLING (BIT NOISE INJECTION)
                if (tx_frame.seq_num == 2 && force_noise_once) {
                    cout << "[FEATURE 3: ERROR HANDLING] Injecting 1-bit channel noise into Frame Seq=2...\n";
                    channel.injectNoiseBit(tx_frame, 0, 3);
                    force_noise_once = false;
                }

                // FEATURE 1: MOVEMENT OF PACKETS (UDP BROADCAST TO PYSHARK)
                cout << "[FEATURE 1: MOVEMENT OF PACKETS] Node 1 -> Channel | Transmitting Frame Seq=" 
                          << (int)tx_frame.seq_num << " over UDP socket 127.0.0.1:9000...\n";
                channel.broadcastToPyShark(tx_frame);
                nodeA.handleSuccess();

                Frame ack_frame = receiver.processFrame(tx_frame);

                cout << "[FEATURE 1: MOVEMENT OF PACKETS] Receiver -> Channel | Transmitting ACK Seq=" 
                          << (int)ack_frame.seq_num << " back to Node 1...\n";
                channel.broadcastToPyShark(ack_frame);

                // FEATURE 4: FLOW CONTROL (PROCESSING SELECTIVE ACK)
                cout << "[FEATURE 4: FLOW CONTROL] Sender processing ACK Seq=" << (int)ack_frame.seq_num << "...\n";
                sender.receiveAck(ack_frame.seq_num);
            }
        } 
        else if (nodeB_wants) {
            Frame tx_frame = nodeB.tx_queue.front();
            cout << "[FEATURE 1: MOVEMENT OF PACKETS] Node 2 -> Channel | Transmitting Collision Payload Frame...\n";
            channel.broadcastToPyShark(tx_frame);
            nodeB.handleSuccess();
        } 
        else {
            cout << "[FEATURE 5: MULTIPLE ACCESS] Slot " << current_slot << " is IDLE (Nodes waiting/backing off).\n";
        }

        // FEATURE 4: FLOW CONTROL (RETRANSMISSION TIMERS CHECK)
        vector<Frame> retransmissions = sender.tickTimers();
        for (const auto& re_frame : retransmissions) {
            cout << "[FEATURE 4: FLOW CONTROL] Queueing Selective Retransmission for Frame Seq=" 
                      << (int)re_frame.seq_num << " into MAC Layer...\n";
            nodeA.tx_queue.push(re_frame);
        }

        current_slot++;
        this_thread::sleep_for(chrono::milliseconds(300));
    }

    // FEATURE 2: IN-ORDER DELIVERY SUMMARY
    cout << "  SIMULATION COMPLETED — FEATURE 2 SUMMARY: IN-ORDER APPLICATION DELIVERY   \n";
    for (size_t i = 0; i < receiver.upper_layer_delivered_data.size(); ++i) {
        cout << "  [FEATURE 2: IN-ORDER DELIVERY] Index " << i << " -> Received Payload: \"" 
                  << receiver.upper_layer_delivered_data[i] << "\"\n";
    }

    return 0;
}