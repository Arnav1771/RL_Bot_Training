"""
Boost-pad utility functions for the Stealth bot.

Provides helpers to find the nearest active boost pad and the "best" pad
considering distance, size, and whether it lies roughly on the path to a target.
"""

import math
from typing import Optional

from util.boost_pad_tracker import BoostPad, BoostPadTracker
from util.vec import Vec3


def find_nearest_active_pad(tracker: BoostPadTracker, car_location: Vec3) -> Optional[BoostPad]:
    """
    Return the closest active (available) boost pad to *car_location*, or None if
    no pads are currently active.
    """
    best_pad: Optional[BoostPad] = None
    best_dist = float('inf')

    for pad in tracker.boost_pads:
        if not pad.is_active:
            continue
        d = car_location.dist(pad.location)
        if d < best_dist:
            best_dist = d
            best_pad = pad

    return best_pad


def find_best_boost_pad(
    tracker: BoostPadTracker,
    car_location: Vec3,
    target_location: Vec3,
    max_detour_angle: float = math.pi / 3,  # 60 degrees
) -> Optional[BoostPad]:
    """
    Select the best active boost pad by scoring each pad on:
      - distance (closer is better)
      - whether it is a full (100) boost canister (bonus)
      - whether it lies roughly on the path from the car toward *target_location*

    *max_detour_angle* controls how far off-course we're willing to detour; pads
    beyond that angle get heavily penalised.

    Returns None when no active pads exist.
    """
    best_pad: Optional[BoostPad] = None
    best_score = float('-inf')

    car_to_target = (target_location - car_location).flat()
    car_to_target_len = car_to_target.length()

    for pad in tracker.boost_pads:
        if not pad.is_active:
            continue

        car_to_pad = (pad.location - car_location).flat()
        pad_dist = car_to_pad.length()

        # Skip pads that are extremely close (we'd drive over them anyway)
        if pad_dist < 50:
            continue

        # --- Angle penalty ---------------------------------------------------
        if car_to_target_len > 100 and pad_dist > 100:
            cos_angle = car_to_pad.dot(car_to_target) / (pad_dist * car_to_target_len)
            cos_angle = max(-1.0, min(1.0, cos_angle))  # clamp for acos safety
            angle = math.acos(cos_angle)
        else:
            angle = 0.0

        if angle > max_detour_angle:
            # Pad is too far off course — apply a heavy penalty but don't skip
            # entirely so that if *all* pads are off-course we still pick one.
            angle_score = -2000.0
        else:
            # Linearly reward being on-course (0° → +500, max_detour_angle → 0)
            angle_score = 500.0 * (1.0 - angle / max_detour_angle)

        # --- Distance score (closer is better) --------------------------------
        distance_score = -pad_dist  # simple: every uu of distance costs 1 point

        # --- Full-boost bonus --------------------------------------------------
        full_bonus = 500.0 if pad.is_full_boost else 0.0

        score = distance_score + angle_score + full_bonus

        if score > best_score:
            best_score = score
            best_pad = pad

    return best_pad
