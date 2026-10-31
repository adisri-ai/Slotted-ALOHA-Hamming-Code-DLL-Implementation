#ifndef HAMMING_CODE_HPP
#define HAMMING_CODE_HPP

#include <iostream>
#include <vector>
#include <cstdint>

class HammingCode {
public:
    // Encodes a 4-bit nibble into a 7-bit Hamming codeword
    // Codeword bit positions (1-indexed): [P1, P2, D1, P4, D2, D3, D4]
    static uint8_t encodeNibble(uint8_t nibble) {
        uint8_t d1 = (nibble >> 3) & 0x01;
        uint8_t d2 = (nibble >> 2) & 0x01;
        uint8_t d3 = (nibble >> 1) & 0x01;
        uint8_t d4 = (nibble >> 0) & 0x01;

        uint8_t p1 = d1 ^ d2 ^ d4;
        uint8_t p2 = d1 ^ d3 ^ d4;
        uint8_t p4 = d2 ^ d3 ^ d4;

        uint8_t codeword = 0;
        codeword |= (p1 << 6); // Bit 1
        codeword |= (p2 << 5); // Bit 2
        codeword |= (d1 << 4); // Bit 3
        codeword |= (p4 << 3); // Bit 4
        codeword |= (d2 << 2); // Bit 5
        codeword |= (d3 << 1); // Bit 6
        codeword |= (d4 << 0); // Bit 7

        return codeword;
    }

    // Decodes a 7-bit Hamming codeword, calculates syndrome, and corrects 1-bit errors
    static uint8_t decodeNibble(uint8_t codeword, bool& error_detected, int& corrected_bit_pos) {
        error_detected = false;
        corrected_bit_pos = 0;

        uint8_t c1 = (codeword >> 6) & 0x01;
        uint8_t c2 = (codeword >> 5) & 0x01;
        uint8_t c3 = (codeword >> 4) & 0x01;
        uint8_t c4 = (codeword >> 3) & 0x01;
        uint8_t c5 = (codeword >> 2) & 0x01;
        uint8_t c6 = (codeword >> 1) & 0x01;
        uint8_t c7 = (codeword >> 0) & 0x01;

        // Calculate Syndrome bits s1, s2, s3
        uint8_t s1 = c1 ^ c3 ^ c5 ^ c7;
        uint8_t s2 = c2 ^ c3 ^ c6 ^ c7;
        uint8_t s3 = c4 ^ c5 ^ c6 ^ c7;

        int syndrome = (s3 << 2) | (s2 << 1) | s1; // 1-based bit position of error

        if (syndrome != 0) {
            error_detected = true;
            corrected_bit_pos = syndrome;
            // Correct the bit by flipping position (7 - syndrome)
            codeword ^= (1 << (7 - syndrome));
        }
        uint8_t d1 = (codeword >> 4) & 0x01;
        uint8_t d2 = (codeword >> 2) & 0x01;
        uint8_t d3 = (codeword >> 1) & 0x01;
        uint8_t d4 = (codeword >> 0) & 0x01;

        return (d1 << 3) | (d2 << 2) | (d3 << 1) | d4;
    }

    // Encodes full byte string payload into Hamming codewords
    static std::vector<uint8_t> encodeBuffer(const std::vector<uint8_t>& input) {
        std::vector<uint8_t> encoded;
        for (uint8_t byte : input) {
            uint8_t high_nibble = (byte >> 4) & 0x0F;
            uint8_t low_nibble = byte & 0x0F;
            encoded.push_back(encodeNibble(high_nibble));
            encoded.push_back(encodeNibble(low_nibble));
        }
        return encoded;
    }

    static std::vector<uint8_t> decodeBuffer(const std::vector<uint8_t>& encoded, int& total_errors_corrected) {
        std::vector<uint8_t> decoded;
        total_errors_corrected = 0;

        for (size_t i = 0; i < encoded.size(); i += 2) {
            bool err1 = false, err2 = false;
            int pos1 = 0, pos2 = 0;

            uint8_t high_nibble = decodeNibble(encoded[i], err1, pos1);
            uint8_t low_nibble = decodeNibble(encoded[i+1], err2, pos2);

            if (err1) {
                total_errors_corrected++;
                std::cout << "[HAMMING FEC] Single-bit error detected at position " << pos1 
                          << " in block " << i << ". Automatically corrected!\n";
            }
            if (err2) {
                total_errors_corrected++;
                std::cout << "[HAMMING FEC] Single-bit error detected at position " << pos2 
                          << " in block " << (i + 1) << ". Automatically corrected!\n";
            }

            decoded.push_back((high_nibble << 4) | low_nibble);
        }
        return decoded;
    }
};

#endif