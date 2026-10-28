#ifndef FRAME_HPP
#define FRAME_HPP

#include <string>
#include <vector>
#include <cstdint>
#include <sstream>

enum FrameType : uint8_t {
    FRAME_DATA = 0,
    FRAME_ACK  = 1,
    FRAME_NAK  = 2
};

struct Frame {
    uint8_t node_id;         // Source node ID
    FrameType type;          // DATA, ACK, or NAK
    uint8_t seq_num;         // Sequence Number
    uint8_t ack_num;         // ACK / Piggybacked ACK Number
    uint8_t payload_len;     // Payload byte length
    std::vector<uint8_t> encoded_payload; // Hamming Encoded Payload Data

    // Formats the frame into a text line for UDP transport to PyShark
    std::string serialize() const {
        std::stringstream ss;
        ss << "NODE:" << (int)node_id 
           << "|TYPE:" << (type == FRAME_DATA ? "DATA" : (type == FRAME_ACK ? "ACK" : "NAK"))
           << "|SEQ:" << (int)seq_num 
           << "|ACK:" << (int)ack_num 
           << "|LEN:" << (int)payload_len 
           << "|PAYLOAD_HAMMING:";
        
        for (uint8_t byte : encoded_payload) {
            ss << std::hex << (int)byte << " ";
        }
        return ss.str();
    }
};

#endif