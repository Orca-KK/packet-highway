"""
main.py
=======

The entry point and the render loop for Packet Highway.

Run it
------
    python main.py --demo        # fake traffic, no admin/Npcap needed
    python main.py               # live capture (run terminal as Administrator)
    python main.py --filter tcp  # live capture, only TCP
    python main.py --iface "Wi-Fi"   # live capture on a named interface

Controls
--------
    ESC / window close : quit
    Click a car        : "follow" it; its details show in the inspector panel
    SPACE              : clear the current selection

The big picture (the render loop)
---------------------------------
Every frame we:
  1. Drain new packets from the queue and turn each into a Car.
  2. update() every car (move it; drop ones that left the screen).
  3. Clear the screen and draw, in order: background, road, cars, then the
     UI panels (dashboard, legend, sign, inspector).
  4. Flip the display and wait so we hit ~FPS frames per second.

That loop runs on the MAIN thread. Packet capture runs on a separate thread
(see capture.py / demo_source.py) and they meet only at PACKET_QUEUE.
"""

from __future__ import annotations

import argparse
import queue
import sys

import pygame

import capture
from car import Car
from config import (
    BASE_SPEED,
    BG_BOTTOM,
    BG_TOP,
    FPS,
    HEIGHT,
    LANE_LINE,
    LANE_YS,
    LEGEND_ORDER,
    NEON,
    PANEL_BG,
    PANEL_BORDER,
    PROTO_STYLE,
    ROAD,
    ROAD_BOTTOM,
    ROAD_TOP,
    TEXT,
    TEXT_DIM,
    TITLE,
    WIDTH,
)


def parse_args():
    p = argparse.ArgumentParser(description="Packet Highway")
    p.add_argument("--demo", action="store_true",
                   help="Use fake traffic instead of live capture.")
    p.add_argument("--iface", default=None,
                   help="Network interface name for live capture.")
    p.add_argument("--filter", default=None, dest="bpf",
                   help='BPF filter for live capture, e.g. "tcp or udp".')
    return p.parse_args()


def make_background(width: int, height: int) -> pygame.Surface:
    """Pre-render the vertical gradient sky once, since it never changes."""
    bg = pygame.Surface((width, height))
    for y in range(height):
        # Linear interpolation between BG_TOP and BG_BOTTOM down the screen.
        t = y / height
        color = tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)
        )
        pygame.draw.line(bg, color, (0, y), (width, y))
    return bg


def draw_road(surface: pygame.Surface, dash_offset: float) -> None:
    """Draw the asphalt band and the moving dashed lane markings."""
    pygame.draw.rect(surface, ROAD, (0, ROAD_TOP, WIDTH, ROAD_BOTTOM - ROAD_TOP))

    # Dashed lines BETWEEN lanes. We have NUM_LANES lanes, so NUM_LANES-1
    # dividers, positioned at the midpoints between adjacent lane centres.
    for i in range(len(LANE_YS) - 1):
        y = int((LANE_YS[i] + LANE_YS[i + 1]) / 2)
        dash_len, gap = 28, 22
        period = dash_len + gap
        # dash_offset scrolls the dashes left so the road looks like it moves.
        start = -int(dash_offset) % period - period
        x = start
        while x < WIDTH:
            pygame.draw.line(surface, LANE_LINE, (x, y), (x + dash_len, y), 3)
            x += period


def draw_panel(surface, rect, title, font_title):
    """Draw a semi-transparent bordered panel with a title; return inner top-y."""
    panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    panel.fill((*PANEL_BG, 205))
    surface.blit(panel, rect.topleft)
    pygame.draw.rect(surface, PANEL_BORDER, rect, 1, border_radius=6)
    if title:
        t = font_title.render(title, True, NEON)
        surface.blit(t, (rect.x + 12, rect.y + 8))
        return rect.y + 32
    return rect.y + 10


def draw_dashboard(surface, fonts) -> None:
    """Top-left panel: live totals from capture.STATS."""
    snap = capture.STATS.snapshot()
    rect = pygame.Rect(16, 16, 250, 150)
    y = draw_panel(surface, rect, "PACKET HIGHWAY", fonts["title"])

    lines = [
        ("packets", f"{snap['total_packets']:,}"),
        ("bytes", f"{snap['total_bytes']:,}"),
        ("protocols", f"{len(snap['by_protocol'])}"),
    ]
    for label, val in lines:
        lt = fonts["body"].render(label, True, TEXT_DIM)
        vt = fonts["body"].render(val, True, TEXT)
        surface.blit(lt, (rect.x + 12, y))
        surface.blit(vt, (rect.right - 12 - vt.get_width(), y))
        y += 24


def draw_legend(surface, fonts) -> None:
    """Bottom-left panel: the protocol -> car colour key, with live counts."""
    snap = capture.STATS.snapshot()
    rect = pygame.Rect(16, HEIGHT - 200, 230, 184)
    y = draw_panel(surface, rect, "PACKET TYPES", fonts["title"])

    for proto in LEGEND_ORDER:
        style = PROTO_STYLE[proto]
        # colour swatch
        pygame.draw.rect(surface, style["color"], (rect.x + 12, y + 2, 16, 12),
                         border_radius=3)
        name = fonts["body"].render(proto, True, TEXT)
        surface.blit(name, (rect.x + 38, y))
        count = snap["by_protocol"].get(proto, 0)
        ct = fonts["body"].render(f"{count:,}", True, TEXT_DIM)
        surface.blit(ct, (rect.right - 12 - ct.get_width(), y))
        y += 26


def draw_sign(surface, fonts) -> None:
    """The glowing 'PACKET HIGHWAY' sign across the upper road."""
    text = fonts["sign"].render("PACKET HIGHWAY", True, NEON)
    # Cheap glow: blit the text a few times offset and faded behind itself.
    cx = WIDTH // 2 - text.get_width() // 2
    cy = ROAD_TOP + 6
    glow = text.copy()
    glow.set_alpha(60)
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        surface.blit(glow, (cx + dx, cy + dy))
    surface.blit(text, (cx, cy))


def draw_inspector(surface, fonts, car) -> None:
    """Right-side panel showing the followed car's packet details."""
    if car is None:
        return
    pkt = car.packet
    rect = pygame.Rect(WIDTH - 270, HEIGHT // 2 - 70, 254, 140)
    y = draw_panel(surface, rect, "FOLLOW CAR", fonts["title"])
    rows = [
        ("proto", pkt.get("proto", "?")),
        ("src", f"{pkt.get('src','?')}:{pkt.get('sport',0)}"),
        ("dst", f"{pkt.get('dst','?')}:{pkt.get('dport',0)}"),
        ("bytes", str(pkt.get("length", 0))),
    ]
    for label, val in rows:
        lt = fonts["small"].render(label, True, TEXT_DIM)
        surface.blit(lt, (rect.x + 12, y))
        vt = fonts["small"].render(str(val), True, TEXT)
        surface.blit(vt, (rect.x + 80, y))
        y += 24
    # Highlight ring around the followed car so you can spot it.
    pygame.draw.circle(surface, NEON, (int(car.x + 25), int(car.y)), 34, 2)


def main() -> None:
    args = parse_args()

    # --- start a packet source on a background thread ----------------------
    if args.demo:
        import demo_source
        demo_source.start()
    else:
        try:
            capture.start(iface=args.iface, bpf_filter=args.bpf)
        except Exception as e:
            print("Could not start live capture:", e)
            print("Tips: install Npcap (https://npcap.com), run your terminal")
            print("as Administrator, or just use:  python main.py --demo")
            sys.exit(1)

    # --- pygame setup ------------------------------------------------------
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    fonts = {
        "title": pygame.font.SysFont("consolas", 14, bold=True),
        "sign": pygame.font.SysFont("consolas", 30, bold=True),
        "body": pygame.font.SysFont("consolas", 14),
        "small": pygame.font.SysFont("consolas", 13),
        "label": pygame.font.SysFont("consolas", 11),
    }

    background = make_background(WIDTH, HEIGHT)
    cars: list[Car] = []
    followed: Car | None = None
    dash_offset = 0.0

    running = True
    while running:
        # 1) handle input events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    followed = None
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                # Find the topmost car under the cursor (search newest first).
                for c in reversed(cars):
                    if c._body_rect().collidepoint(mx, my):
                        followed = c
                        break

        # 2) drain the packet queue -> spawn cars
        #    Cap how many we pull per frame so a flood can't stall the loop.
        for _ in range(40):
            try:
                pkt = capture.PACKET_QUEUE.get_nowait()
            except queue.Empty:
                break
            cars.append(Car(pkt))

        # Keep the car list from growing without bound.
        if len(cars) > 400:
            cars = cars[-400:]

        # 3) update motion
        for c in cars:
            c.update()
        cars = [c for c in cars if c.alive]
        if followed is not None and not followed.alive:
            followed = None

        dash_offset += BASE_SPEED  # scroll the road markings

        # 4) draw everything
        screen.blit(background, (0, 0))
        draw_road(screen, dash_offset)
        draw_sign(screen, fonts)
        for c in cars:
            c.draw(screen, fonts["label"])
        draw_dashboard(screen, fonts)
        draw_legend(screen, fonts)
        draw_inspector(screen, fonts, followed)

        # footer hint
        hint = fonts["small"].render(
            "click a car to follow it  -  SPACE clears  -  ESC quits",
            True, TEXT_DIM,
        )
        screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 24))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
