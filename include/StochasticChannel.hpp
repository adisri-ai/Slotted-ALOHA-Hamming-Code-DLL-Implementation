#ifndef STOCHASTIC_CHANNEL_HPP
#define STOCHASTIC_CHANNEL_HPP

#include "Frame.hpp"
#include <random>
#include <vector>
#include <iostream>
using namespace std;
struct ChannelConfig {
    double noise_probability; 
    double drop_probability;  
};

class StochasticChannel {
private:
    mt19937 rng;
    bernoulli_distribution noise_dist;
    bernoulli_distribution drop_dist;

public:
    StochasticChannel(double noise_p = 0.25, double drop_p = 0.15)
        : rng(random_device{}()),
          noise_dist(noise_p),
          drop_dist(drop_p) {}

    bool shouldDropPacket() {
        return drop_dist(rng);
    }

    bool shouldInjectNoise() {
        return noise_dist(rng);
    }

    void injectRandomBitFlip(Frame& frame) {
        if (frame.encoded_payload.empty()) return;

        uniform_int_distribution<size_t> byte_dist(0, frame.encoded_payload.size() - 1);
        uniform_int_distribution<int> bit_dist(0, 7);

        size_t target_byte = byte_dist(rng);
        int target_bit = bit_dist(rng);

        frame.encoded_payload[target_byte] ^= (1 << target_bit);
        cout << "[FEATURE 3: ERROR HANDLING - STOCHASTIC CHANNEL] Injected random 1-bit noise at payload byte [" 
                  << target_byte << "], bit position [" << target_bit << "].\n";
    }
};

#endif