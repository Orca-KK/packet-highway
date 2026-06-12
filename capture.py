"""
capture.py
==========

Live network packet capture for Packet Highway.

This module is responsible for ONE thing: grabbing packets off your network
interface and turning each one into a small, plain Python dictionary that the
rest of the program understands. It deliberately knows nothing about cars,
colours, or pygame -- that separation is what makes the project easy to study.

How it works
------------
We use Scapy's `sniff()` function. Scapy hands us a packet object for every
frame it sees. We pull out a few fields (protocol, source/destination IP,
ports, length) and push a simplified dict onto a thread-safe queue. The
visualizer thread later pops items off that queue to spawn cars.

Why a separate thread?
----------------------
`sniff()` blocks -- it runs forever, calling our callback for each packet. If we
ran it on the main thread, the pygame window would freeze. So capture runs on a
background (daemon) thread and communicates with the main thread only through
the queue. The queue is the one shared object, and queue.Queue is already
thread-safe, so we don't need our own locks.

Windows note
------------
Scapy needs Npcap installed (https://npcap.com). During Npcap setup, tick
"Install Npcap in WinPcap API-compatible Mode". You must run your terminal /
VS Code "as Administrator" for capture to work, because reading raw packets is
a privileged operation.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field

# Scapy is imported lazily inside start() so that the rest of the program
# (and the --demo mode) can run even on a machine where Scapy/Npcap aren't set
# up yet. Importing scapy at module load time would crash immediately.


# A queue with a max size so that, if packets arrive faster than we can draw
# them, we drop the excess instead of eating all your RAM. maxsize is a knob
# you can tune.
PACKET_QUEUE: "queue.Queue[dict]" = queue.Queue(maxsize=2000)


@dataclass
class CaptureStats:
    """Running totals, shown in the on-screen dashboard.

    A dataclass is just a class where Python writes __init__ for us. Each field
    below becomes an attribute. We protect the counters with a lock because the
    capture thread writes them while the draw thread reads them.
    """

    total_packets: int = 0
    # protocol name -> count, e.g. {"TCP": 1024, "UDP": 88}
    by_protocol: dict[str, int] = field(default_factory=dict)
    total_bytes: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, proto: str, length: int) -> None:
        """Thread-safe update of the counters for one packet."""
        with self._lock:
            self.total_packets += 1
            self.total_bytes += length
            self.by_protocol[proto] = self.by_protocol.get(proto, 0) + 1

    def snapshot(self) -> dict:
        """Return a plain copy of the stats so the UI can read without locking."""
        with self._lock:
            return {
                "total_packets": self.total_packets,
                "total_bytes": self.total_bytes,
                "by_protocol": dict(self.by_protocol),
            }


# One shared stats object for the whole program.
STATS = CaptureStats()


def _classify(pkt) -> dict | None:
    """Convert a raw Scapy packet into our simplified dict.

    Returns None for packets we don't care about (e.g. ones with no IP layer),
    which the caller simply skips.

    The returned dict shape -- this is the "contract" between capture and the
    visualizer:

        {
            "proto":   str,   # "TCP" | "UDP" | "ICMP" | "DNS" | "ARP" | "OTHER"
            "src":     str,   # source IP (or MAC for ARP)
            "dst":     str,   # destination IP
            "sport":   int,   # source port, 0 if not applicable
            "dport":   int,   # destination port, 0 if not applicable
            "length":  int,   # packet size in bytes
            "t":       float, # time.time() when captured
        }
    """
    # Imported here (after start() has imported scapy) so this stays optional.
    from scapy.layers.inet import IP, TCP, UDP, ICMP
    from scapy.layers.l2 import ARP
    from scapy.layers.dns import DNS

    info = {
        "proto": "OTHER",
        "src": "?",
        "dst": "?",
        "sport": 0,
        "dport": 0,
        "length": len(pkt),
        "t": time.time(),
    }

    # ARP packets live at layer 2 and have no IP layer, so handle them first.
    if pkt.haslayer(ARP):
        info["proto"] = "ARP"
        info["src"] = pkt[ARP].psrc
        info["dst"] = pkt[ARP].pdst
        return info

    # Everything else we care about rides on IP.
    if not pkt.haslayer(IP):
        return None

    ip = pkt[IP]
    info["src"] = ip.src
    info["dst"] = ip.dst

    if pkt.haslayer(TCP):
        tcp = pkt[TCP]
        info["sport"] = int(tcp.sport)
        info["dport"] = int(tcp.dport)
        # DNS often rides on UDP, but TCP DNS exists; check the DNS layer.
        info["proto"] = "DNS" if pkt.haslayer(DNS) else "TCP"
    elif pkt.haslayer(UDP):
        udp = pkt[UDP]
        info["sport"] = int(udp.sport)
        info["dport"] = int(udp.dport)
        info["proto"] = "DNS" if pkt.haslayer(DNS) else "UDP"
    elif pkt.haslayer(ICMP):
        info["proto"] = "ICMP"

    return info


def _on_packet(pkt) -> None:
    """Scapy callback: runs once per captured packet on the capture thread."""
    info = _classify(pkt)
    if info is None:
        return
    STATS.record(info["proto"], info["length"])
    try:
        # put_nowait raises queue.Full instead of blocking. We'd rather drop a
        # packet from the *display* than stall the capture thread.
        PACKET_QUEUE.put_nowait(info)
    except queue.Full:
        pass


def _sniff_loop(iface: str | None, bpf_filter: str | None) -> None:
    """The body of the capture thread. Calls scapy.sniff(), which blocks."""
    from scapy.all import sniff

    # store=False  -> don't keep packets in memory (we only stream them out)
    # prn          -> our per-packet callback
    # iface        -> which network card; None lets Scapy pick a default
    # filter       -> a BPF filter string, e.g. "tcp or udp", or None for all
    sniff(prn=_on_packet, store=False, iface=iface, filter=bpf_filter)


def start(iface: str | None = None, bpf_filter: str | None = None) -> threading.Thread:
    """Start capturing on a background daemon thread and return that thread.

    Parameters
    ----------
    iface : str | None
        Interface name. On Windows, list options with
        `python -c "from scapy.all import get_if_list; print(get_if_list())"`.
        Pass None to let Scapy choose.
    bpf_filter : str | None
        Optional Berkeley Packet Filter, e.g. "tcp", "udp or icmp",
        "port 443". None captures everything.

    The returned thread is a daemon, meaning it dies automatically when the main
    program exits -- you don't have to clean it up by hand.
    """
    # Touch scapy now so a misconfigured machine fails here with a clear error,
    # not deep inside the thread where it's harder to see.
    import scapy.all  # noqa: F401

    t = threading.Thread(
        target=_sniff_loop,
        args=(iface, bpf_filter),
        name="packet-capture",
        daemon=True,
    )
    t.start()
    return t
