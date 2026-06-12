"""
config.py
=========

All the "knobs" and lookup tables for the visual side, kept in one place so you
can re-theme the highway without hunting through the rendering code.

The central idea of the project lives here: PROTO_STYLE maps each protocol to a
car type. Different packet type => different car. Tweak these freely.
"""

# ---- Window ----------------------------------------------------------------
WIDTH = 1100
HEIGHT = 640
FPS = 60
TITLE = "Packet Highway"

# ---- Colours (R, G, B) -----------------------------------------------------
BG_TOP = (8, 12, 28)        # night sky at the top of the screen
BG_BOTTOM = (16, 22, 44)    # slightly lighter near the road
ROAD = (24, 26, 34)
LANE_LINE = (90, 96, 120)
TEXT = (210, 220, 240)
TEXT_DIM = (130, 140, 165)
PANEL_BG = (10, 14, 30)
PANEL_BORDER = (40, 60, 110)
NEON = (0, 220, 255)        # the "PACKET HIGHWAY" sign glow

# ---- Lanes -----------------------------------------------------------------
# Each lane is a horizontal band the cars drive along. y is the vertical
# centre of the lane. More lanes = more parallel "streams" of traffic.
NUM_LANES = 5
ROAD_TOP = 150
ROAD_BOTTOM = HEIGHT - 110
# Computed lane centre y-positions, evenly spaced inside the road area.
LANE_YS = [
    ROAD_TOP + (i + 0.5) * (ROAD_BOTTOM - ROAD_TOP) / NUM_LANES
    for i in range(NUM_LANES)
]

# ---- The mapping: protocol -> car style ------------------------------------
# Each entry describes how to draw that protocol's car:
#   color  : body colour
#   kind   : a shape hint the renderer understands
#            "sedan" | "truck" | "bug" | "van" | "sport" | "bike"
#   label  : short tag drawn near the car
#
# Design choice: bigger/heavier protocols get bigger vehicles. TCP (the
# workhorse of the internet) is a sedan; bulk UDP is a van; ICMP (tiny control
# pings) is a little bug; ARP (local link chatter) is a bike; DNS (quick
# lookups) is a nippy sport car; anything unknown is a generic truck.
PROTO_STYLE = {
    "TCP":   {"color": (60, 130, 255),  "kind": "sedan", "label": "TCP"},
    "UDP":   {"color": (255, 170, 40),  "kind": "van",   "label": "UDP"},
    "DNS":   {"color": (120, 230, 140), "kind": "sport", "label": "DNS"},
    "ICMP":  {"color": (235, 90, 90),   "kind": "bug",   "label": "ICMP"},
    "ARP":   {"color": (200, 120, 235), "kind": "bike",  "label": "ARP"},
    "OTHER": {"color": (150, 160, 180), "kind": "truck", "label": "???"},
}

# Order used in the legend panel (bottom-left).
LEGEND_ORDER = ["TCP", "UDP", "DNS", "ICMP", "ARP", "OTHER"]

# ---- Motion ----------------------------------------------------------------
BASE_SPEED = 3.2            # base pixels/frame a car moves leftward
SPEED_JITTER = 1.4          # +/- random variation per car so they don't clump
