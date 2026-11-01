#ifndef HAMMING_CODE_HPP
#define HAMMING_CODE_HPP

#include <vector>
#include <cstdint>
#include <iostream>
using namespace std;
class HammingCode {
public:
    uint32_t n_bits; 
    uint32_t k_bits; 

    HammingCode(uint32_t n = 7, uint32_t k = 4) : n_bits(n), k_bits(k) {}

    static uint8_t encodeNibble(uint8_t nibble) {
        uint8_t d1 = (nibble >> 3) & 0x01;
        uint8_t d2 = (nibble >> 2) & 0x01;
        uint8_t d3 = (nibble >> 1) & 0x01;
        uint8_t d4 = nibble & 0x01;

        uint8_t p1 = d1 ^ d2 ^ d4;
        uint8_t p2 = d1 ^ d3 ^ d4;
        uint8_t p4 = d2 ^ d3 ^ d4;

        return (p1 << 6) | (p2 << 5) | (d1 << 4) | (p4 << 3) | (d2 << 2) | (d3 << 1) | d4;
    }

    static uint8_t decodeNibble(uint8_t codeword, bool& error_corrected) {
        error_corrected = false;
        
        uint8_t p1 = (codeword >> 6) & 0x01;
        uint8_t p2 = (codeword >> 5) & 0x01;
        uint8_t d1 = (codeword >> 4) & 0x01;
        uint8_t p4 = (codeword >> 3) & 0x01;
        uint8_t d2 = (codeword >> 2) & 0x01;
        uint8_t d3 = (codeword >> 1) & 0x01;
        uint8_t d4 = codeword & 0x01;

        uint8_t s1 = p1 ^ d1 ^ d2 ^ d4;
        uint8_t s2 = p2 ^ d1 ^ d3 ^ d4;
        uint8_t s4 = p4 ^ d2 ^ d3 ^ d4;

        int syndrome = (s4 << 2) | (s2 << 1) | s1;

        if (syndrome != 0) {
            error_corrected = true;
            cout << "[HAMMING FEC (" << 7 << "," << 4 << ")] Single-bit error detected at position " 
                      << syndrome << ". Automatically corrected!\n";
            codeword ^= (1 << (7 - syndrome));
            
            d1 = (codeword >> 4) & 0x01;
            d2 = (codeword >> 2) & 0x01;
            d3 = (codeword >> 1) & 0x01;
            d4 = codeword & 0x01;
        }

        return (d1 << 3) | (d2 << 2) | (d3 << 1) | d4;
    }

    static vector<uint8_t> encodeBuffer(const vector<uint8_t>& input) {
        vector<uint8_t> output;
        for (uint8_t b : input) {
            output.push_back(encodeNibble((b >> 4) & 0x0F));
            output.push_back(encodeNibble(b & 0x0F));
        }
        return output;
    }

    static vector<uint8_t> decodeBuffer(const vector<uint8_t>& input, int& total_errors_corrected) {
        vector<uint8_t> output;
        total_errors_corrected = 0;
        for (size_t i = 0; i + 1 < input.size(); i += 2) {
            bool err1 = false, err2 = false;
            uint8_t high = decodeNibble(input[i], err1);
            uint8_t low = decodeNibble(input[i+1], err2);
            if (err1) total_errors_corrected++;
            if (err2) total_errors_corrected++;
            output.push_back((high << 4) | low);
        }
        return output;
    }

    static vector<uint8_t> decodeBuffer(const vector<uint8_t>& input) {
        int dummy = 0;
        return decodeBuffer(input, dummy);
    }
};

#endif