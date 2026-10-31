#ifndef SLOTTED_ALOHA_HPP
#define SLOTTED_ALOHA_HPP

#include "Frame.hpp"
#include <queue>
#include <iostream>
#include <cstdlib>
#include <algorithm>
using namespace std;
class Node {
public:
    uint8_t node_id;
    queue<Frame> tx_queue;
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
            cout << "[FEATURE 5: MULTIPLE ACCESS] Node " << (int)node_id 
                      << " in backoff state. " << backoff_slots << " slot(s) remaining.\n";
            return false;
        }
        return true;
    }

    void handleCollision() {
        collision_count++;
        // Binary Exponential Backoff: Delay between [1, 2^k - 1] slots
        int max_backoff = (1 << min(collision_count, 4)) - 1;
        backoff_slots = (rand() % max(max_backoff, 1)) + 1;
        cout << "[FEATURE 5: MULTIPLE ACCESS] Node " << (int)node_id 
                  << " COLLISION DETECTED! Exponential Backoff set to " << backoff_slots << " slots.\n";
    }

    void handleSuccess() {
        collision_count = 0;
        backoff_slots = 0;
        if (!tx_queue.empty()) tx_queue.pop();
    }
};

#endif