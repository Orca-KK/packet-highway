"""
demo_source.py
==============

A fake packet generator.

Why this exists
---------------
Real capture needs Npcap installed and an Administrator terminal. That's a
hurdle when you just want to see the highway move, or when you're studying the
visualizer code and don't want to deal with drivers yet. This module produces
realistic-looking random packets and pushes them onto the SAME queue that
capture.py uses, so the rest of the program can't tell the difference.

Run the app with `--demo` to use this instead of live capture.
"""

from __future__ import annotations

import random
import threading
import time

from capture import PACKET_QUEUE, STATS

# Weighted protocol mix that roughly resembles ordinary web browsing traffic.
# (proto, weight) -- higher weight = appears more often.
_MIX = [
    ("TCP", 50),
    ("UDP", 20),
    ("DNS", 12),
    ("ICMP", 5),
    ("ARP", 3),
    ("OTHER", 10),
]
_PROTOS = [p for p, _ in _MIX]
_WEIGHTS = [w for _, w in _MIX]

_COMMON_PORTS = [80, 443, 53, 22, 8080, 3389, 123, 5353]


def _random_ip() -> str:
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


def _make_fake_packet() -> dict:
    proto = random.choices(_PROTOS, weights=_WEIGHTS, k=1)[0]
    # Length distributions differ a bit by protocol, just for flavour.
    if proto in ("TCP", "OTHER"):
        length = random.randint(60, 1500)
    elif proto == "UDP":
        length = random.randint(60, 800)
    elif proto == "DNS":
        length = random.randint(60, 300)
    else:  # ICMP, ARP
        length = random.randint(42, 98)

    return {
        "proto": proto,
        "src": _random_ip(),
        "dst": _random_ip(),
        "sport": random.choice(_COMMON_PORTS),
        "dport": random.choice(_COMMON_PORTS),
        "length": length,
        "t": time.time(),
    }


def _loop() -> None:
    while True:
        pkt = _make_fake_packet()
        STATS.record(pkt["proto"], pkt["length"])
        try:
            PACKET_QUEUE.put_nowait(pkt)
        except Exception:
            pass
        # Random gaps so traffic arrives in uneven bursts, like the real thing.
        time.sleep(random.uniform(0.02, 0.25))


def start() -> threading.Thread:
    """Start the fake traffic generator on a daemon thread."""
    t = threading.Thread(target=_loop, name="demo-source", daemon=True)
    t.start()
    return t
