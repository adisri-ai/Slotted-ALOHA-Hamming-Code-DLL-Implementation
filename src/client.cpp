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

int main(int argc, char* argv[]) {
    uint8_t node_id = (argc > 1) ? std::stoi(argv[1]) : 1;

    std::cout << "===========================================================================\n";
    std::cout << "  DATA LINK LAYER CLIENT (NODE ID: " << (int)node_id << ")\n";
    std::cout << "===========================================================================\n";

#if defined(_WIN32) || defined(_WIN64)
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
#endif

    int client_sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(8000); // Connects to Server on Port 8000
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    // Non-blocking socket configuration
#if defined(_WIN32) || defined(_WIN64)
    u_long mode = 1;
    ioctlsocket(client_sock, FIONBIO, &mode);
#else
    fcntl(client_sock, F_SETFL, O_NONBLOCK);
#endif

    SelectiveRepeatSender sender(4, 8);
    Node mac_node(node_id);

    if (node_id == 1) {
        std::vector<std::string> messages = {"Packet-0", "Packet-1", "Packet-2", "Packet-3"};
        for (const auto& msg : messages) {
            std::vector<uint8_t> raw_bytes(msg.begin(), msg.end());
            sender.sendPacket(node_id, raw_bytes);
        }
        for (auto& pair : sender.window_buffer) {
            mac_node.tx_queue.push(pair.second.frame);
        }
    } else {
        // Node 2 sends a single frame to induce a Slotted ALOHA collision in Slot 1
        Frame col_frame;
        col_frame.node_id = node_id;
        col_frame.type = FRAME_DATA;
        col_frame.seq_num = 99;
        col_frame.encoded_payload = HammingCode::encodeBuffer({'C', 'L'});
        mac_node.tx_queue.push(col_frame);
    }

    int current_slot = 1;
    while ((!mac_node.tx_queue.empty() || !sender.window_buffer.empty()) && current_slot <= 12) {
        std::this_thread::sleep_for(std::chrono::milliseconds(300));

        if (mac_node.canTransmitInSlot()) {
            Frame tx_frame = mac_node.tx_queue.front();
            std::string serialized = tx_frame.serialize();

            // Transmit Frame over UDP socket to Server
            sendto(client_sock, serialized.c_str(), serialized.length(), 0, 
                   (struct sockaddr*)&server_addr, sizeof(server_addr));

            std::cout << "[FEATURE 1: MOVEMENT OF PACKETS] Client Node " << (int)node_id 
                      << " -> Server | Transmitted Frame Seq=" << (int)tx_frame.seq_num << "\n";
            
            mac_node.handleSuccess();
        }

        // Listen non-blocking for incoming ACK from Server
        char buffer[1024] = {0};
        int bytes = recv(client_sock, buffer, sizeof(buffer) - 1, 0);
        if (bytes > 0) {
            buffer[bytes] = '\0';
            std::string ack_str(buffer);
            size_t seq_pos = ack_str.find("SEQ:");
            if (seq_pos != std::string::npos) {
                int ack_seq = std::stoi(ack_str.substr(seq_pos + 4));
                std::cout << "[FEATURE 4: FLOW CONTROL] Client Node " << (int)node_id 
                          << " received ACK for Seq=" << ack_seq << "\n";
                sender.receiveAck(ack_seq);
            }
        }

        // Tick retransmission timers
        std::vector<Frame> retransmissions = sender.tickTimers();
        for (const auto& re_frame : retransmissions) {
            std::cout << "[FEATURE 4: FLOW CONTROL] Client Node " << (int)node_id 
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