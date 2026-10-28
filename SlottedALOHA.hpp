#ifndef SLOTTED_ALOHA_HPP
#define SLOTTED_ALOHA_HPP

#include "Frame.hpp"
#include <queue>
#include <iostream>
#include <cstdlib>

class Node {
public:
    uint8_t node_id;
    std::queue<Frame> tx_queue;
    int backoff_slots;
    int collision_count;

    Node(uint8_t id) : node_id(id), backoff_slots(0), collision_count(0) {}

    bool hasPendingFrame() {
        return !tx_queue.empty();
    }

    bool canTransmitInSlot() {
        if (!hasPendingFrame()) return false;
        if (backoff_slots > 0) {
            backoff_slots--;
            std::cout << "[ALOHA MAC] Node " << (int)node_id << " backing off. Remaining delay: " << backoff_slots << " slots.\n";
            return false;
        }
        return true;
    }

    void handleCollision() {
        collision_count++;
        // Binary Exponential Backoff: Choose random delay between [1, 2^k - 1]
        int max_backoff = (1 << std::min(collision_count, 4)) - 1;
        backoff_slots = (rand() % max_backoff) + 1;
        std::cout << "[ALOHA MAC] Node " << (int)node_id << " COLLISION! Backing off for " << backoff_slots << " time slots.\n";
    }

    void handleSuccess() {
        collision_count = 0;
        backoff_slots = 0;
        if (!tx_queue.empty()) tx_queue.pop(); // Remove transmitted frame
    }
};

#endif