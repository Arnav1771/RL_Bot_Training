# Stealth Bot — Implementation Plan

## Overview

Complete gameplay upgrade for the **Stealth** Rocket League bot, transforming it from a simple ball-chaser into a bot that kicks off, shoots, defends, manages boost, and controls the car intelligently.

---

## Features Implemented

### 1. Kickoff Routine
**File:** `src/util/kickoff.py` *(new)*

| Detail | Description |
|--------|-------------|
| **Detection** | `is_kickoff()` checks `packet.game_info.is_kickoff_pause` and also whether the ball is near the origin and stationary (fallback). |
| **Execution** | `kickoff_sequence()` returns a `Sequence` of `ControlStep`s: full throttle + boost toward ball → jump → dodge forward into ball. |
| **Timing** | Boost phase duration scales linearly with spawn distance (clamped 0.4–1.4 s) so it works from any kickoff position. |

---

### 2. Shooting / Offense
**File:** `src/bot.py` — `_find_hittable_intercept()`

| Detail | Description |
|--------|-------------|
| **Intercept finder** | Scans ball prediction (up to 3 s ahead) for the earliest slice with `z < 300` (hittable height). |
| **Shot aiming** | Computes a target point offset **behind** the ball relative to the opponent goal, so contact pushes the ball goalward. |
| **Reachability check** | Only commits to the intercept if estimated travel time ≤ 1.5× available time. |
| **Fallback** | If no hittable slice is found, predicts ball 2 s ahead (far away) or aims directly at the ball (close). |
| **Goal coordinates** | Team 0 → opponent goal at `y = +5120`; Team 1 → `y = −5120`. |

---

### 3. Defensive Rotation
**File:** `src/bot.py` — `_ball_on_our_side()`, `_ball_behind_us()`, `_between_ball_and_own_goal()`, `_defensive_rotation_target()`

| Detail | Description |
|--------|-------------|
| **State detection** | Ball on our half AND behind us → DEFENSE mode. |
| **Challenge** | If the car is already between ball and own goal, drive toward the ball (CHALLENGE). |
| **Rotate back** | Otherwise, drive to a point 800 uu in front of our goal line, shifted toward ball's x-position so we don't just park in goal centre. |
| **Own goal coords** | Team 0 → `y = −5120`; Team 1 → `y = +5120`. |

---

### 4. Boost Management
**File:** `src/util/boost_utils.py` *(new)*

| Function | Description |
|----------|-------------|
| `find_nearest_active_pad()` | Returns closest active boost pad by Euclidean distance. |
| `find_best_boost_pad()` | Scores each active pad by: **distance** (closer = better), **full-boost bonus** (+500), **alignment** with travel direction (pads beyond 60° detour angle are penalised −2000). |
| **Integration** | In `bot.py`, if boost < 20 and the bot is not in CHALLENGE or OFFENSE state, it detours to the best pad. |

---

### 5. Car Control Improvements
**File:** `src/util/drive.py` *(modified)*

| Function | Description |
|----------|-------------|
| `angle_to_target()` | Returns yaw angle (rad) from car's forward to the target. |
| `desired_speed_for_angle_and_distance()` | Heuristic target speed: 2300 (lined up, far), 1400 (lined up, close), 1200 (medium turn), 600 (sharp turn). |
| `throttle_to_reach_speed()` | Proportional controller mapping speed error → throttle (500 uu/s = full). |
| `should_use_handbrake()` | True when angle > 1.55 rad and speed > 800 uu/s. |
| `should_boost()` | Conservative: only when on wheels, boost > 1, angle < 0.2 rad, distance > 1200, target speed ≥ 2200, current speed < 2200. |
| `get_speed_from_throttle()` | Returns 1410 (throttle only) or 2300 (boosting) — useful for time-to-reach estimates. |
| `half_flip_sequence()` | Returns a `Sequence`: reverse throttle → back-flip → cancel flip with forward pitch + air-roll 180° → land. Used when car faces completely wrong way. |

---

### 6. Bot Priority System (get_output)
**File:** `src/bot.py`

```
Priority Order:
1. Continue active Sequence (kickoff, dodge, half-flip)
2. Kickoff detection → kickoff_sequence()
3. Game-state classification:
   a. OFFENSE — ball not on our side, or not behind us
   b. DEFENSE — ball on our side AND behind us
4. OFFENSE path:
   - Find hittable intercept → aim shot toward opponent goal
   - Fallback: predict ball 2 s ahead or aim directly
5. DEFENSE path:
   - CHALLENGE if between ball and own goal
   - ROTATE back to defensive position otherwise
6. LOW BOOST detour (boost < 20) — best pad via find_best_boost_pad()
7. Half-flip if facing > 2.5 rad away, slow, on ground
8. Dodge-to-accelerate if lined up, far away, mid-speed, on ground
9. Compute final controls: steer, throttle, boost, handbrake
```

---

## Files Summary

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `src/bot.py` | **Rewritten** | ~354 | Main bot logic with full priority system |
| `src/util/drive.py` | **Extended** | ~130 | All driving/control helpers |
| `src/util/kickoff.py` | **New** | ~74 | Kickoff detection + sequence |
| `src/util/boost_utils.py` | **New** | ~97 | Boost pad selection logic |
| `src/util/orientation.py` | Unchanged | — | Orientation + relative_location |
| `src/util/vec.py` | Unchanged | — | Vec3 math |
| `src/util/sequence.py` | Unchanged | — | Sequence / ControlStep framework |
| `src/util/boost_pad_tracker.py` | Unchanged | — | Boost pad state tracking |
| `src/util/ball_prediction_analysis.py` | Unchanged | — | Ball prediction utilities |
| `src/util/spikes.py` | Unchanged | — | Spike-ball detection |

---

## How to Test

1. Open RLBot GUI and load the Stealth bot.
2. Start a match (the default `rlbot.cfg` runs 1v1 with two copies of Stealth).
3. Observe in-game rendering — the bot now labels its state (`OFFENSE`, `ROTATE`, `CHALLENGE`, `BOOST`, etc.) above the car along with speed.
4. Key behaviours to look for:
   - **Kickoff:** bot boosts + front-flips toward ball at the start of each round.
   - **Shooting:** bot leads the ball and approaches from behind it (relative to opponent goal).
   - **Defense:** bot rotates back when the ball is behind it on its own half.
   - **Boost pickup:** bot detours to nearby pads when boost < 20.
   - **Half-flip:** bot performs a half-flip when facing completely the wrong way.
   - **Handbrake:** bot powerslides for sharp turns instead of doing a wide arc.

---

## Future Improvements

- **Aerial hits** — jump + boost toward high-altitude ball slices.
- **Dribbling / flicks** — carry the ball on the car roof and flick it.
- **Wall play** — read wall bounces and drive up the wall.
- **Demolitions** — target opponents when they're vulnerable.
- **Team play** — pass, rotate with a teammate, avoid double-committing.
- **Recovery** — wave-dash on landing, air-roll to land on wheels faster.
