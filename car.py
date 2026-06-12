"""
car.py
======

The Car class. One Car == one captured packet, drawn as a vehicle that drives
across the screen.

A Car is a small bundle of state (position, speed, which lane, what it looks
like) plus two methods: update() to move it one frame, and draw() to paint it.
This is the classic "sprite" pattern in game programming, written by hand so
you can see exactly what every line does.
"""

from __future__ import annotations

import random
from math import sin as _sin

import pygame

from config import (
    BASE_SPEED,
    LANE_YS,
    PROTO_STYLE,
    SPEED_JITTER,
    WIDTH,
)


class Car:
    def __init__(self, packet: dict):
        """Build a car from a packet dict (the contract from capture.py)."""
        self.packet = packet
        proto = packet.get("proto", "OTHER")
        # Fall back to OTHER's style if we somehow see an unknown protocol.
        self.style = PROTO_STYLE.get(proto, PROTO_STYLE["OTHER"])

        # Pick a lane at random and read its vertical centre from config.
        self.lane = random.randrange(len(LANE_YS))
        self.y = LANE_YS[self.lane]

        # Cars enter from the right edge and drive left (toward x = 0).
        self.x = float(WIDTH + 40)

        # Each car gets a slightly different speed so traffic looks organic.
        self.speed = BASE_SPEED + random.uniform(-SPEED_JITTER, SPEED_JITTER)

        # Bigger packets => longer vehicle, clamped to a sane range.
        length = packet.get("length", 100)
        self.size = max(0.7, min(2.0, length / 600.0))  # scale factor

        # A little vertical bob to keep things lively (purely cosmetic).
        self.bob_phase = random.uniform(0, 6.28)

        self.alive = True

    def update(self) -> None:
        """Advance one frame. Mark the car dead once it leaves the screen."""
        self.x -= self.speed
        self.bob_phase += 0.15
        if self.x < -80:
            self.alive = False

    # -- drawing helpers ----------------------------------------------------
    def _body_rect(self) -> pygame.Rect:
        kind = self.style["kind"]
        # Base dimensions per vehicle kind (width, height), before size scale.
        dims = {
            "sedan": (54, 22),
            "van":   (62, 28),
            "truck": (74, 30),
            "sport": (50, 18),
            "bug":   (34, 20),
            "bike":  (30, 14),
        }[kind]
        w = int(dims[0] * self.size)
        h = int(dims[1] * self.size)
        # A small vertical "bob" (a few pixels of sine wave) so cars feel alive.
        y = int(self.y + 3 * _sin(self.bob_phase)) - h // 2
        return pygame.Rect(int(self.x), y, w, h)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        """Paint the car (and its label) onto the given surface."""
        color = self.style["color"]
        rect = self._body_rect()

        # Body: a rounded rectangle. Different kinds get small tweaks so they
        # read as distinct vehicle silhouettes even at a glance.
        pygame.draw.rect(surface, color, rect, border_radius=6)

        kind = self.style["kind"]
        if kind in ("sedan", "sport", "van", "truck"):
            # Cabin: a lighter inset rectangle suggesting windows.
            cabin = rect.inflate(-int(rect.width * 0.45), -int(rect.height * 0.4))
            cabin.centerx = rect.centerx + int(rect.width * 0.05)
            light = tuple(min(255, c + 60) for c in color)
            pygame.draw.rect(surface, light, cabin, border_radius=4)

        # Headlights: two small yellow dots at the front (left) edge.
        hl = (255, 240, 180)
        r = max(2, int(2 * self.size))
        pygame.draw.circle(surface, hl, (rect.left + 2, rect.top + 4), r)
        pygame.draw.circle(surface, hl, (rect.left + 2, rect.bottom - 4), r)

        # Wheels: dark dots under the body.
        wheel = (12, 12, 16)
        wy = rect.bottom
        for wx in (rect.left + rect.width // 4, rect.right - rect.width // 4):
            pygame.draw.circle(surface, wheel, (wx, wy), max(2, int(3 * self.size)))

        # Label above the car (e.g. "TCP").
        tag = font.render(self.style["label"], True, (235, 240, 250))
        surface.blit(tag, (rect.centerx - tag.get_width() // 2, rect.top - 16))
