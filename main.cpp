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
    cout << "=========================================================\n";
    cout << "  DATA LINK LAYER SIMULATION (ALOHA, HAMMING, SR-ARQ)   \n";
    cout << "=========================================================\n\n";

    ChannelSimulator channel;
    SelectiveRepeatSender sender(4, 8);
    SelectiveRepeatReceiver receiver(4, 8);

    Node nodeA(1); // Sender Node 1
    Node nodeB(2); // Sender Node 2 (Used to simulate ALOHA collisions)

    // Prepare message payloads
    vector<string> messages = {"Packet-0", "Packet-1", "Packet-2", "Packet-3"};

    // Buffer packets into Selective Repeat Sender
    for (const auto& msg : messages) {
        vector<uint8_t> raw_bytes(msg.begin(), msg.end());
        sender.sendPacket(nodeA.node_id, raw_bytes);
    }

    // Populate Node A's MAC Queue
    for (auto& pair : sender.window_buffer) {
        nodeA.tx_queue.push(pair.second.frame);
    }

    // Populate Node B's MAC Queue with a dummy frame to force a collision in Slot 1
    Frame collision_frame;
    collision_frame.node_id = nodeB.node_id;
    collision_frame.type = FRAME_DATA;
    collision_frame.seq_num = 99;
    collision_frame.encoded_payload = HammingCode::encodeBuffer({'C', 'L'});
    nodeB.tx_queue.push(collision_frame);

    int current_slot = 1;
    bool force_noise_once = true;
    bool simulate_packet_drop = true; // Drop Packet-1 once to show out-of-order buffering & retransmission

    while (!nodeA.tx_queue.empty() || !nodeB.tx_queue.empty() || !sender.window_buffer.empty()) {
        cout << "\n---------------------------------------------------------\n";
        cout << "=== TIME SLOT " << current_slot << " ===\n";
        cout << "---------------------------------------------------------\n";

        // Step 1: Slotted ALOHA MAC Contention Check
        bool nodeA_wants = nodeA.canTransmitInSlot();
        bool nodeB_wants = nodeB.canTransmitInSlot();

        if (nodeA_wants && nodeB_wants) {
            // Collision Event
            cout << "[CHANNEL] Collision detected in Slot " << current_slot 
                      << "! Both Node A and Node B transmitted simultaneously.\n";
            nodeA.handleCollision();
            nodeB.handleCollision();
        } 
        else if (nodeA_wants) {
            // Successful transmission slot for Node A
            Frame tx_frame = nodeA.tx_queue.front();

            // Simulate Loss of Packet-1 on its first attempt
            if (tx_frame.seq_num == 1 && simulate_packet_drop) {
                cout << "[CHANNEL DROP] Frame Seq=1 was LOST in transit over the channel!\n";
                nodeA.handleSuccess(); // Remove from MAC queue, but remains unACKed in SR Sender
                simulate_packet_drop = false;
            } 
            else {
                // Simulate Noise Injection into Packet-2 to test Hamming FEC
                if (tx_frame.seq_num == 2 && force_noise_once) {
                    channel.injectNoiseBit(tx_frame, 0, 3); // Flip bit at byte 0, bit index 3
                    force_noise_once = false;
                }

                // Broadcast frame over UDP socket to PyShark
                channel.broadcastToPyShark(tx_frame);
                nodeA.handleSuccess();

                // Step 2: Receiver processes frame with Hamming Code and Selective Repeat
                Frame ack_frame = receiver.processFrame(tx_frame);

                // Broadcast ACK to PyShark
                channel.broadcastToPyShark(ack_frame);

                // Sender receives ACK
                sender.receiveAck(ack_frame.seq_num);
            }
        } 
        else if (nodeB_wants) {
            // Node B transmits dummy collision payload
            Frame tx_frame = nodeB.tx_queue.front();
            channel.broadcastToPyShark(tx_frame);
            nodeB.handleSuccess();
            cout << "[CHANNEL] Node B transmitted successfully in Slot " << current_slot << "\n";
        } 
        else {
            cout << "[CHANNEL] Slot " << current_slot << " is IDLE or nodes are backing off.\n";
        }

        // Step 3: Tick Selective Repeat Retransmission Timers
        vector<Frame> retransmissions = sender.tickTimers();
        for (const auto& re_frame : retransmissions) {
            nodeA.tx_queue.push(re_frame); // Queue retransmission into MAC layer
        }

        current_slot++;
        this_thread::sleep_for(chrono::milliseconds(400));
    }

    cout << "\n=========================================================\n";
    cout << "  SIMULATION COMPLETED SUCCESSFULLY                     \n";
    cout << "=========================================================\n";
    cout << "In-Order Application Layer Messages Delivered:\n";
    for (const auto& msg : receiver.upper_layer_delivered_data) {
        cout << "  [APP RECEIVED]: " << msg << "\n";
    }

    return 0;
}