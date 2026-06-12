# Packet Highway

Live network packets visualized as cars on a highway. Each packet your machine
sees becomes a vehicle, and the **type of packet decides the type of car**
(TCP = sedan, UDP = van, DNS = sport car, ICMP = bug, ARP = bike, anything
else = truck). A dashboard tracks live totals, and you can click any car to
"follow" it and inspect the underlying packet.

This is a from-scratch re-implementation built for learning. The code is
heavily commented so you can read it top to bottom.

---

## Quick start (Windows + VS Code)

### 1. Install Python
If you don't have it: install Python 3.11+ from python.org. During setup, tick
**"Add Python to PATH"**.

### 2. Get the project into VS Code
Put all the `.py` files in one folder, then open that folder in VS Code
(`File > Open Folder`). Open a terminal inside VS Code with `` Ctrl+` ``.

### 3. Create a virtual environment (recommended)
```powershell
python -m venv .venv
.venv\Scripts\activate
```
You should see `(.venv)` at the start of your prompt.

### 4. Install dependencies
```powershell
pip install -r requirements.txt
```

### 5. Run it in DEMO mode first (no special setup needed)
```powershell
python main.py --demo
```
This uses fake, randomly generated traffic. If a highway window opens with cars
driving across it, your install works. **Start here.**

---

## Running on REAL network traffic

Capturing real packets needs two extra things on Windows:

### A. Install Npcap
Download from **https://npcap.com** and install it. During setup, tick:
- **"Install Npcap in WinPcap API-compatible Mode"**

### B. Run as Administrator
Reading raw packets is privileged. Close VS Code, right-click it, choose
**"Run as administrator"**, reopen your folder, re-activate the venv, then:
```powershell
python main.py
```

Useful variations:
```powershell
python main.py --filter "tcp or udp"     # only TCP/UDP packets
python main.py --filter "port 443"       # only HTTPS traffic
python main.py --iface "Wi-Fi"           # capture on a specific interface
```

List your interface names:
```powershell
python -c "from scapy.all import get_if_list; print(get_if_list())"
```

### Generating traffic to watch
Open a browser, run `ping google.com` (makes ICMP "bug" cars), or stream a
video (lots of TCP sedans). DNS lookups appear when you visit new sites.

---

## Controls

| Action            | Effect                                   |
|-------------------|------------------------------------------|
| Click a car       | Follow it; details show in the inspector |
| `SPACE`           | Clear the current selection              |
| `ESC` / close box | Quit                                     |

---

## How the project is organized

The code is split so each file has one clear job. Read them in this order:

```
config.py        <- all the "knobs": colors, lane layout, and the
                    PROTOCOL -> CAR mapping (the heart of the project)
capture.py       <- live packet capture (Scapy) on a background thread,
                    plus a thread-safe queue and stats counters
demo_source.py   <- fake traffic generator, so you can run without Npcap
car.py           <- the Car class: one packet drawn as one moving vehicle
main.py          <- the pygame window, the render loop, and the UI panels
```

### The data flow (how a packet becomes a car)

```
  Network card
       |
       v
  [ capture thread ]              ( background thread )
   scapy.sniff()  --> _classify() turns a raw packet into a small dict:
                       {proto, src, dst, sport, dport, length, t}
       |
       v
  PACKET_QUEUE  (thread-safe queue.Queue)   <-- the ONLY shared object
       |
       v
  [ main thread ]                 ( pygame render loop )
   pull dicts --> new Car(dict) --> update() each frame --> draw()
```

The two threads never touch each other's data directly. They communicate only
through `PACKET_QUEUE`. This is the key design idea: capturing can't freeze the
animation, and drawing can't slow down capturing.

### The render loop (in `main.py`)

Every frame (~60 times/second) the program:
1. Reads keyboard/mouse events.
2. Drains new packets off the queue and creates a `Car` for each.
3. Calls `update()` on every car (moves it left; removes off-screen ones).
4. Draws background, road, cars, then UI panels.
5. Flips the display and sleeps to hold the frame rate.

---

## Things to try (to actually sharpen your skills)

These are ordered easy -> harder. Each touches a different concept.

1. **Re-theme it.** Change colors and the `PROTO_STYLE` car shapes in
   `config.py`. (Reading config-driven code.)
2. **Add a new protocol.** Detect HTTPS specifically (TCP on port 443) in
   `capture._classify` and give it its own car style. (Branching + mapping.)
3. **Per-lane meaning.** Make the lane depend on protocol instead of random, so
   each protocol gets its own lane. (Edit `Car.__init__` and `config`.)
4. **Speed = packet size.** Make bigger packets drive slower (trucks are slow).
   (Tweak `Car.speed`.)
5. **Pause / resume.** Add a `P` key that freezes updates. (Event handling +
   state.)
6. **Top talkers panel.** Track which source IPs send the most packets and show
   a leaderboard. (Dictionaries + sorting + a new draw function.)
7. **Save a capture.** Write each packet dict to a CSV as it arrives, so you can
   replay later. (File I/O + a `--record` flag.)
8. **Replay mode.** Read that CSV back through the same queue instead of live
   capture. (You'll see why the queue abstraction was worth it.)

---

## Troubleshooting

**The window opens but no cars appear (live mode).**
You're probably not capturing. Check: Npcap installed? Terminal running as
Administrator? Try `--demo` to confirm the visualizer itself works, then try a
specific `--iface`.

**`ImportError` / Scapy errors on startup.**
`pip install -r requirements.txt` inside your activated venv. For *live*
capture you also need Npcap (demo mode doesn't).

**It's slow / laggy with lots of traffic.**
Add a `--filter` to capture less (e.g. `"tcp"`), or lower the car cap / queue
size in `config.py` and `capture.py`.

**Permission denied when capturing.**
Run the terminal as Administrator.

---

## How this maps to the original

The original was an AI (Claude Fable 5) writing this kind of program in one go.
Functionally it's the same two-part system everyone building this lands on:
a **packet sniffer** feeding a **2D animation**. The specific car shapes,
colors, and panels here are choices you can and should change — that's where
the learning is.
