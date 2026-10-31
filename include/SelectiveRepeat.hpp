#ifndef SELECTIVE_REPEAT_HPP
#define SELECTIVE_REPEAT_HPP

#include "Frame.hpp"
#include "HammingCode.hpp"
#include <vector>
#include <map>
#include <iostream>
#include <algorithm>
using namespace std;
class SelectiveRepeatSender {
public:
    int window_size;
    int max_seq_num;
    int send_base;
    int next_seq_num;

    struct PacketState {
        Frame frame;
        bool acked;
        int timer;
    };

    map<int, PacketState> window_buffer;

    SelectiveRepeatSender(int window_sz = 4, int max_seq = 8) 
        : window_size(window_sz), max_seq_num(max_seq), send_base(0), next_seq_num(0) {}

    bool canSend() {
        return (window_buffer.size() < static_cast<size_t>(window_size));
    }

    void sendPacket(uint8_t node_id, const vector<uint8_t>& raw_data) {
        if (!canSend()) {
            cout << "[SR SENDER] Window full! Cannot send packet with Seq=" << next_seq_num << "\n";
            return;
        }

        Frame f;
        f.node_id = node_id;
        f.type = FRAME_DATA;
        f.seq_num = next_seq_num;
        f.ack_num = 0;
        f.encoded_payload = HammingCode::encodeBuffer(raw_data);
        f.payload_len = static_cast<uint8_t>(raw_data.size());

        window_buffer[next_seq_num] = {f, false, 3}; // Timeout set to 3 time slots
        cout << "[SR SENDER] Frame created & buffered: Seq=" << (int)f.seq_num << "\n";
        
        next_seq_num = (next_seq_num + 1) % max_seq_num;
    }

    void receiveAck(int ack_seq) {
        if (window_buffer.find(ack_seq) != window_buffer.end()) {
            window_buffer[ack_seq].acked = true;
            cout << "[SR SENDER] Received Selective ACK for Seq=" << ack_seq << "\n";

            // Slide window base if lowest sequence number is acknowledged
            while (!window_buffer.empty() && window_buffer[send_base].acked) {
                cout << "[SR SENDER] Sliding Window Base forward from Seq=" << send_base << "\n";
                window_buffer.erase(send_base);
                send_base = (send_base + 1) % max_seq_num;
            }
        }
    }

    // Ticks down retransmission timers for unACKed frames in current window
    vector<Frame> tickTimers() {
        vector<Frame> retransmit_queue;
        for (auto& pair : window_buffer) {
            if (!pair.second.acked) {
                pair.second.timer--;
                if (pair.second.timer <= 0) {
                    cout << "[SR TIMEOUT] Retransmission timer expired for Seq=" << pair.first << "! Retransmitting...\n";
                    pair.second.timer = 3; // Reset timer
                    retransmit_queue.push_back(pair.second.frame);
                }
            }
        }
        return retransmit_queue;
    }
};

class SelectiveRepeatReceiver {
public:
    int window_size;
    int max_seq_num;
    int rcv_base;

    map<int, Frame> rcv_buffer;
    vector<string> upper_layer_delivered_data;

    SelectiveRepeatReceiver(int window_sz = 4, int max_seq = 8) 
        : window_size(window_sz), max_seq_num(max_seq), rcv_base(0) {}

    bool inWindow(int seq) {
        for (int i = 0; i < window_size; i++) {
            if (((rcv_base + i) % max_seq_num) == seq) return true;
        }
        return false;
    }

    Frame processFrame(Frame frame) {
        int errors_corrected = 0;
        vector<uint8_t> clean_payload = HammingCode::decodeBuffer(frame.encoded_payload, errors_corrected);
        string payload_str(clean_payload.begin(), clean_payload.end());

        int seq = frame.seq_num;
        cout << "[SR RECEIVER] Processing Frame Seq=" << seq << " Payload: \"" << payload_str << "\"\n";

        Frame ack_frame;
        ack_frame.node_id = 0; // Receiver ID
        ack_frame.type = FRAME_ACK;
        ack_frame.seq_num = seq; // Selective ACK for this exact packet

        if (inWindow(seq)) {
            rcv_buffer[seq] = frame;

            if (seq == rcv_base) {
                cout << "[SR RECEIVER] In-Order Packet Seq=" << seq << " received. Delivering to Application Layer...\n";
                
                while (rcv_buffer.find(rcv_base) != rcv_buffer.end()) {
                    int num_corrected = 0;
                    vector<uint8_t> data_bytes = HammingCode::decodeBuffer(rcv_buffer[rcv_base].encoded_payload, num_corrected);
                    string delivered_msg(data_bytes.begin(), data_bytes.end());
                    
                    upper_layer_delivered_data.push_back(delivered_msg);
                    cout << "   ---> Delivered to Upper Layer: \"" << delivered_msg << "\" (Seq=" << rcv_base << ")\n";
                    
                    rcv_buffer.erase(rcv_base);
                    rcv_base = (rcv_base + 1) % max_seq_num;
                }
                cout << "[SR RECEIVER] Receiver Window advanced. New Base Seq=" << rcv_base << "\n";
            } else {
                cout << "[SR RECEIVER] Out-of-Order Packet Seq=" << seq << " received (Expected Base=" << rcv_base << "). Buffering frame.\n";
            }
        } else {
            cout << "[SR RECEIVER] Duplicate or Out-of-Window Packet Seq=" << seq << " discarded. Resending ACK.\n";
        }

        return ack_frame;
    }
};

#endif