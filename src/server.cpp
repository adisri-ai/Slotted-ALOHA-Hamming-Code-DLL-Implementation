#include <iostream>
#include <vector>
#include <string>
#include <thread>
#include <chrono>
#include <cstring>

#include "HammingCode.hpp"
#include "Frame.hpp"
#include "SelectiveRepeat.hpp"

#if defined(_WIN32) || defined(_WIN64)
    #include <winsock2.h>
    #pragma comment(lib, "ws2_32.lib")
    typedef int socklen_t;
#else
    #include <sys/socket.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    #include <fcntl.h>
#endif

using namespace std;

Frame parseSerializedFrame(const string& raw) {
    Frame f;
    f.node_id = 1;
    f.type = FRAME_DATA;
    f.seq_num = 0;
    f.ack_num = 0;
    f.payload_len = 0;

    size_t node_pos = raw.find("NODE:");
    if (node_pos != string::npos) f.node_id = stoi(raw.substr(node_pos + 5));

    size_t type_pos = raw.find("TYPE:");
    if (type_pos != string::npos) {
        string t = raw.substr(type_pos + 5, 4);
        if (t.find("ACK") != string::npos) f.type = FRAME_ACK;
        else if (t.find("NAK") != string::npos) f.type = FRAME_NAK;
        else f.type = FRAME_DATA;
    }

    size_t seq_pos = raw.find("SEQ:");
    if (seq_pos != string::npos) f.seq_num = stoi(raw.substr(seq_pos + 4));

    size_t len_pos = raw.find("LEN:");
    if (len_pos != string::npos) f.payload_len = stoi(raw.substr(len_pos + 4));

    size_t payload_pos = raw.find("PAYLOAD_HAMMING:");
    if (payload_pos != string::npos) {
        string hex_str = raw.substr(payload_pos + 16);
        size_t space_pos = 0;
        while ((space_pos = hex_str.find(' ')) != string::npos) {
            string token = hex_str.substr(0, space_pos);
            if (!token.empty()) {
                f.encoded_payload.push_back(static_cast<uint8_t>(stoi(token, nullptr, 16)));
            }
            hex_str.erase(0, space_pos + 1);
        }
    }
    return f;
}

int main(int argc, char* argv[]) {
    // Parse the 3 dynamic CLI parameters
    uint32_t timeout_ms = (argc > 1) ? stoi(argv[1]) : 1000;
    uint32_t hamming_n  = (argc > 2) ? stoi(argv[2]) : 7;
    uint32_t hamming_k  = (argc > 3) ? stoi(argv[3]) : 4;

    cout << "  DATA LINK LAYER SERVER (RECEIVER NODE & CHANNEL MASTER ON PORT 8000)\n";
    cout << "  [CONFIG] Timeout: " << timeout_ms << "ms | Hamming Code: (" 
         << hamming_n << "," << hamming_k << ")\n\n";

#if defined(_WIN32) || defined(_WIN64)
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);
#endif

    int server_sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in server_addr, client_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(8000);
    server_addr.sin_addr.s_addr = INADDR_ANY;

    bind(server_sock, (struct sockaddr*)&server_addr, sizeof(server_addr));

#if defined(_WIN32) || defined(_WIN64)
    u_long mode = 1;
    ioctlsocket(server_sock, FIONBIO, &mode);
#else
    fcntl(server_sock, F_SETFL, O_NONBLOCK);
#endif

    int pyshark_sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in pyshark_addr;
    memset(&pyshark_addr, 0, sizeof(pyshark_addr));
    pyshark_addr.sin_family = AF_INET;
    pyshark_addr.sin_port = htons(9000);
    pyshark_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    SelectiveRepeatReceiver receiver(4, 8);
    HammingCode hamming(hamming_n, hamming_k);
    int current_slot = 1;
    bool force_noise_once = true;

    cout << "[SERVER] Listening for Client connections on UDP Port 8000...\n";

    while (current_slot <= 15) {
        cout << "=== TIME SLOT " << current_slot << " ===\n";
        vector<pair<Frame, sockaddr_in>> slot_frames;
        auto slot_start = chrono::steady_clock::now();
        while (chrono::duration_cast<chrono::milliseconds>(
                   chrono::steady_clock::now() - slot_start).count() < 300) {
            char buffer[1024] = {0};
            socklen_t addr_len = sizeof(client_addr);
            int bytes_read = recvfrom(server_sock, buffer, sizeof(buffer) - 1, 0, 
                                      (struct sockaddr*)&client_addr, &addr_len);
            if (bytes_read > 0) {
                buffer[bytes_read] = '\0';
                Frame f = parseSerializedFrame(buffer);
                slot_frames.push_back({f, client_addr});
            }
            this_thread::sleep_for(chrono::milliseconds(10));
        }

        if (slot_frames.size() > 1) {
            cout << "[FEATURE 5: MULTIPLE ACCESS] COLLISION DETECTED in Slot " << current_slot 
                 << "! Received " << slot_frames.size() << " client frames simultaneously.\n";
            cout << "[FEATURE 5: MULTIPLE ACCESS] Discarding garbled frames. Clients will time out and back off.\n";
        }
        else if (slot_frames.size() == 1) {
            Frame rx_frame = slot_frames[0].first;
            sockaddr_in sender_client = slot_frames[0].second;

            cout << "[FEATURE 1: MOVEMENT OF PACKETS] Server received Frame from Client Node " 
                 << (int)rx_frame.node_id << " | Seq=" << (int)rx_frame.seq_num << "\n";

            if (rx_frame.seq_num == 2 && force_noise_once) {
                cout << "[FEATURE 3: ERROR HANDLING] Injecting 1-bit channel noise into Frame Seq=2...\n";
                if (!rx_frame.encoded_payload.empty()) {
                    rx_frame.encoded_payload[0] ^= 0x10;
                }
                force_noise_once = false;
            }

            string pyshark_msg = rx_frame.serialize();
            sendto(pyshark_sock, pyshark_msg.c_str(), pyshark_msg.length(), 0, 
                   (struct sockaddr*)&pyshark_addr, sizeof(pyshark_addr));

            Frame ack_frame = receiver.processFrame(rx_frame);

            cout << "[FEATURE 4: FLOW CONTROL] Server sending Selective ACK Seq=" 
                 << (int)ack_frame.seq_num << " back to Client Node " << (int)rx_frame.node_id << "...\n";
            string ack_serialized = ack_frame.serialize();
            sendto(server_sock, ack_serialized.c_str(), ack_serialized.length(), 0, 
                   (struct sockaddr*)&sender_client, sizeof(sender_client));

            sendto(pyshark_sock, ack_serialized.c_str(), ack_serialized.length(), 0, 
                   (struct sockaddr*)&pyshark_addr, sizeof(pyshark_addr));
        }
        else {
            cout << "[FEATURE 5: MULTIPLE ACCESS] Slot " << current_slot << " is IDLE.\n";
        }

        current_slot++;
    }

    cout << "  SERVER SIMULATION COMPLETED — IN-ORDER APPLICATION DELIVERY SUMMARY      \n";
    for (size_t i = 0; i < receiver.upper_layer_delivered_data.size(); ++i) {
        cout << "  [FEATURE 2: IN-ORDER DELIVERY] Index " << i << " -> Delivered Payload: \"" 
             << receiver.upper_layer_delivered_data[i] << "\"\n";
    }

#if defined(_WIN32) || defined(_WIN64)
    closesocket(server_sock);
    closesocket(pyshark_sock);
    WSACleanup();
#else
    close(server_sock);
    close(pyshark_sock);
#endif

    return 0;
}