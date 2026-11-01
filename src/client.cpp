#include <iostream>
#include <vector>
#include <string>
#include <thread>
#include <chrono>
#include <cstring>

#include "HammingCode.hpp"
#include "Frame.hpp"
#include "SelectiveRepeat.hpp"
#include "SlottedALOHA.hpp"

#if defined(_WIN32) || defined(_WIN64)
    #include <winsock2.h>
    #pragma comment(lib, "ws2_32.lib")
#else
    #include <sys/socket.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #include <fcntl.h>
#endif

using namespace std;

int main(int argc, char* argv[]) {
    // Parse dynamic parameters: node_id, timeout_ms, hamming_n, hamming_k
    uint8_t node_id     = (argc > 1) ? stoi(argv[1]) : 1;
    uint32_t timeout_ms = (argc > 2) ? stoi(argv[2]) : 1000;
    uint32_t hamming_n  = (argc > 3) ? stoi(argv[3]) : 7;
    uint32_t hamming_k  = (argc > 4) ? stoi(argv[4]) : 4;

    cout << "  DATA LINK LAYER CLIENT (NODE ID: " << (int)node_id << ")\n";
    cout << "  [CONFIG] Timeout: " << timeout_ms << "ms | Hamming Code: (" 
         << hamming_n << "," << hamming_k << ")\n";

#if defined(_WIN32) || defined(_WIN64)
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
#endif

    int client_sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(8000); 
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

#if defined(_WIN32) || defined(_WIN64)
    u_long mode = 1;
    ioctlsocket(client_sock, FIONBIO, &mode);
#else
    fcntl(client_sock, F_SETFL, O_NONBLOCK);
#endif

    SelectiveRepeatSender sender(4, 8);
    Node mac_node(node_id);
    HammingCode hamming(hamming_n, hamming_k);

    if (node_id == 1) {
        vector<string> messages = {"Packet-0", "Packet-1", "Packet-2", "Packet-3"};
        for (const auto& msg : messages) {
            vector<uint8_t> raw_bytes(msg.begin(), msg.end());
            sender.sendPacket(node_id, raw_bytes);
        }
        for (auto& pair : sender.window_buffer) {
            mac_node.tx_queue.push(pair.second.frame);
        }
    } else {
        Frame col_frame;
        col_frame.node_id = node_id;
        col_frame.type = FRAME_DATA;
        col_frame.seq_num = 99;
        col_frame.encoded_payload = HammingCode::encodeBuffer({'C', 'L'});
        mac_node.tx_queue.push(col_frame);
    }

    int current_slot = 1;
    while ((!mac_node.tx_queue.empty() || !sender.window_buffer.empty()) && current_slot <= 12) {
        this_thread::sleep_for(chrono::milliseconds(300));

        if (mac_node.canTransmitInSlot()) {
            Frame tx_frame = mac_node.tx_queue.front();
            string serialized = tx_frame.serialize();

            sendto(client_sock, serialized.c_str(), serialized.length(), 0, 
                   (struct sockaddr*)&server_addr, sizeof(server_addr));

            cout << "[FEATURE 1: MOVEMENT OF PACKETS] Client Node " << (int)node_id 
                 << " -> Server | Transmitted Frame Seq=" << (int)tx_frame.seq_num << "\n";
            
            mac_node.handleSuccess();
        }

        char buffer[1024] = {0};
        int bytes = recv(client_sock, buffer, sizeof(buffer) - 1, 0);
        if (bytes > 0) {
            buffer[bytes] = '\0';
            string ack_str(buffer);
            size_t seq_pos = ack_str.find("SEQ:");
            if (seq_pos != string::npos) {
                int ack_seq = stoi(ack_str.substr(seq_pos + 4));
                cout << "[FEATURE 4: FLOW CONTROL] Client Node " << (int)node_id 
                     << " received ACK for Seq=" << ack_seq << "\n";
                sender.receiveAck(ack_seq);
            }
        }

        vector<Frame> retransmissions = sender.tickTimers(timeout_ms);
        for (const auto& re_frame : retransmissions) {
            cout << "[FEATURE 4: FLOW CONTROL] Client Node " << (int)node_id 
                 << " Retransmission Timer expired for Seq=" << (int)re_frame.seq_num << ". Re-queuing...\n";
            mac_node.tx_queue.push(re_frame);
            mac_node.handleCollision();
        }

        current_slot++;
    }

#if defined(_WIN32) || defined(_WIN64)
    closesocket(client_sock);
    WSACleanup();
#else
    close(client_sock);
#endif

    return 0;
}