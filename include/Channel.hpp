#ifndef CHANNEL_HPP
#define CHANNEL_HPP

#include "Frame.hpp"
#include "SlottedALOHA.hpp"
#include <vector>
#include <iostream>
#include <cstring>

#if defined(_WIN32) || defined(_WIN64)
    #include <winsock2.h>
    #pragma comment(lib, "ws2_32.lib")
#else
    #include <sys/socket.h>
    #include <arpa/inet.h>
    #include <unistd.h>
#endif

class ChannelSimulator {
private:
    int udp_sock;
    struct sockaddr_in pyshark_addr;

public:
    ChannelSimulator() {
#if defined(_WIN32) || defined(_WIN64)
        WSADATA wsaData;
        WSAStartup(MAKEWORD(2,2), &wsaData);
#endif
        udp_sock = socket(AF_INET, SOCK_DGRAM, 0);
        memset(&pyshark_addr, 0, sizeof(pyshark_addr));
        pyshark_addr.sin_family = AF_INET;
        pyshark_addr.sin_port = htons(9000); // UDP Port for PyShark inspection
        pyshark_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    }

    ~ChannelSimulator() {
#if defined(_WIN32) || defined(_WIN64)
        closesocket(udp_sock);
        WSACleanup();
#else
        close(udp_sock);
#endif
    }

    void broadcastToPyShark(const Frame& frame) {
        std::string serialized = frame.serialize();
        sendto(udp_sock, serialized.c_str(), serialized.length(), 0, 
               (struct sockaddr*)&pyshark_addr, sizeof(pyshark_addr));
    }
    void injectNoiseBit(Frame& frame, int byte_index, int bit_index) {
        if (byte_index < static_cast<int>(frame.encoded_payload.size())) {
            frame.encoded_payload[byte_index] ^= (1 << (7 - bit_index));
            std::cout << "[CHANNEL NOISE] Injected 1-bit flip error into Frame Seq=" 
                      << (int)frame.seq_num << " at Byte " << byte_index << ", Bit " << bit_index << "\n";
        }
    }
};

#endif