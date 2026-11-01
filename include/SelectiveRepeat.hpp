#ifndef SELECTIVE_REPEAT_HPP
#define SELECTIVE_REPEAT_HPP

#include "Frame.hpp"
#include "HammingCode.hpp"
#include <map>
#include <vector>
#include <iostream>
#include <chrono>
using namespace std;
struct SenderFrame {
    Frame frame;
    bool acked;
    chrono::steady_clock::time_point send_time;
};

class SelectiveRepeatSender {
public:
    uint32_t window_size;
    uint32_t max_seq;
    uint32_t send_base;
    uint32_t next_seq_num;
    map<uint32_t, SenderFrame> window_buffer;

    SelectiveRepeatSender(uint32_t w_size = 4, uint32_t m_seq = 8)
        : window_size(w_size), max_seq(m_seq), send_base(0), next_seq_num(0) {}

    bool sendPacket(uint8_t node_id, const vector<uint8_t>& payload) {
        if (next_seq_num < send_base + window_size) {
            Frame f;
            f.node_id = node_id;
            f.type = FRAME_DATA;
            f.seq_num = next_seq_num % max_seq;
            f.ack_num = 0;
            f.payload_len = payload.size();
            f.encoded_payload = HammingCode::encodeBuffer(payload);

            SenderFrame sf = {f, false, chrono::steady_clock::now()};
            window_buffer[f.seq_num] = sf;
            next_seq_num++;
            return true;
        }
        return false;
    }

    void receiveAck(uint32_t ack_seq) {
        if (window_buffer.count(ack_seq)) {
            window_buffer[ack_seq].acked = true;
            cout << "[SR SENDER] Marked Frame Seq=" << ack_seq << " as ACKED.\n";
            
            while (!window_buffer.empty() && window_buffer.begin()->second.acked) {
                cout << "[SR SENDER] Sliding Window Base advanced past Seq=" 
                          << window_buffer.begin()->first << "\n";
                window_buffer.erase(window_buffer.begin());
                send_base++;
            }
        }
    }

    vector<Frame> tickTimers(uint32_t timeout_ms = 1000) {
        vector<Frame> timed_out_frames;
        auto now = chrono::steady_clock::now();
        for (auto& pair : window_buffer) {
            if (!pair.second.acked) {
                auto elapsed = chrono::duration_cast<chrono::milliseconds>(now - pair.second.send_time).count();
                if (elapsed >= timeout_ms) {
                    timed_out_frames.push_back(pair.second.frame);
                    pair.second.send_time = now;
                }
            }
        }
        return timed_out_frames;
    }
};

class SelectiveRepeatReceiver {
public:
    uint32_t window_size;
    uint32_t max_seq;
    uint32_t rcv_base;
    map<uint32_t, vector<uint8_t>> rcv_buffer;
    vector<string> upper_layer_delivered_data;

    SelectiveRepeatReceiver(uint32_t w_size = 4, uint32_t m_seq = 8)
        : window_size(w_size), max_seq(m_seq), rcv_base(0) {}

    Frame processFrame(Frame& rx_frame) {
        Frame ack;
        ack.node_id = rx_frame.node_id;
        ack.type = FRAME_ACK;
        ack.seq_num = rx_frame.seq_num;

        int errors_corrected = 0;
        vector<uint8_t> decoded = HammingCode::decodeBuffer(rx_frame.encoded_payload, errors_corrected);

        if (rx_frame.seq_num >= rcv_base && rx_frame.seq_num < rcv_base + window_size) {
            rcv_buffer[rx_frame.seq_num] = decoded;

            if (rx_frame.seq_num == rcv_base) {
                while (rcv_buffer.count(rcv_base)) {
                    string payload_str(rcv_buffer[rcv_base].begin(), rcv_buffer[rcv_base].end());
                    upper_layer_delivered_data.push_back(payload_str);
                    cout << "[SR RECEIVER] In-Order Delivery -> App Received: \"" << payload_str << "\"\n";
                    rcv_buffer.erase(rcv_base);
                    rcv_base++;
                    cout << "[SR RECEIVER] Sliding Window Base advanced to Base=" << rcv_base << "\n";
                }
            } else {
                cout << "[SR RECEIVER] Out-of-Order Packet Seq=" << rx_frame.seq_num 
                          << " received (Expected Base=" << rcv_base << "). Buffering frame.\n";
            }
        }
        return ack;
    }
};

#endif