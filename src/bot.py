"""
Stealth – a Rocket League bot built on the RLBot framework.

Priority system in get_output():
  1. Continue any active Sequence (kickoff, dodge, half-flip, …)
  2. Kickoff routine if a kickoff is detected
  3. Determine game state: OFFENSE vs DEFENSE
  4. OFFENSE – find a hittable ball-prediction slice, aim shot toward opponent goal
  5. DEFENSE – rotate back toward own goal or challenge the ball
  6. LOW BOOST – detour to pick up the best nearby boost pad
  7. Apply car controls (throttle, boost, handbrake, dodge-to-accelerate)
"""

import math

from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.ball_prediction_analysis import find_slice_at_time, find_matching_slice
from util.boost_pad_tracker import BoostPadTracker
from util.drive import (
    angle_to_target,
    desired_speed_for_angle_and_distance,
    half_flip_sequence,
    should_boost,
    should_use_handbrake,
    steer_toward_target,
    throttle_to_reach_speed,
)
from util.kickoff import is_kickoff, kickoff_sequence
from util.orientation import Orientation
from util.sequence import Sequence, ControlStep
from util.vec import Vec3


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FIELD_HALF_LENGTH = 5120.0  # Goal-line y coordinate
GOAL_CENTER_X = 0.0
HITTABLE_Z_THRESHOLD = 300.0  # Ball must be below this height to be "hittable"
SHOT_OFFSET_DISTANCE = 200.0  # Offset behind ball so we push it goalward
LOW_BOOST_THRESHOLD = 20.0  # Below this we start looking for boost pads
PREDICTION_SECONDS = 3.0  # How far into the future to search for intercepts


class MyBot(BaseAgent):
    """Main bot class – wires together kickoff, offense, defense, boost management."""

    def __init__(self, name, team, index):
        super().__init__(name, team, index)
        self.active_sequence: Sequence = None
        self.boost_pad_tracker = BoostPadTracker()
        self._last_dodge_time: float = -999.0

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize_agent(self):
        """Called once when the game has started and field info is available."""
        self.boost_pad_tracker.initialize_boosts(self.get_field_info())

    # ------------------------------------------------------------------
    # Goal helpers – depend on self.team
    # ------------------------------------------------------------------

    @property
    def opponent_goal_y(self) -> float:
        """Y coordinate of the centre of the opponent's goal."""
        return FIELD_HALF_LENGTH if self.team == 0 else -FIELD_HALF_LENGTH

    @property
    def own_goal_y(self) -> float:
        """Y coordinate of the centre of our own goal."""
        return -FIELD_HALF_LENGTH if self.team == 0 else FIELD_HALF_LENGTH

    @property
    def opponent_goal_location(self) -> Vec3:
        return Vec3(GOAL_CENTER_X, self.opponent_goal_y, 0)

    @property
    def own_goal_location(self) -> Vec3:
        return Vec3(GOAL_CENTER_X, self.own_goal_y, 0)

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        """Called every frame.  Returns controls for this tick."""

        # --- Housekeeping ---------------------------------------------------
        self.boost_pad_tracker.update_boost_status(packet)

        # 1.  Continue an active sequence (kickoff, dodge, half-flip, …)
        if self.active_sequence is not None and not self.active_sequence.done:
            controls = self.active_sequence.tick(packet)
            if controls is not None:
                return controls

        # --- Gather state ---------------------------------------------------
        my_car = packet.game_cars[self.index]
        car_location = Vec3(my_car.physics.location)
        car_velocity = Vec3(my_car.physics.velocity)
        ball_location = Vec3(packet.game_ball.physics.location)
        car_speed = car_velocity.length()
        has_wheel_contact = bool(getattr(my_car, 'has_wheel_contact', True))
        boost_amount = float(getattr(my_car, 'boost', getattr(my_car, 'boost_amount', 0.0)))
        seconds = float(packet.game_info.seconds_elapsed)

        # 2.  Kickoff ---------------------------------------------------------
        if is_kickoff(packet):
            self.active_sequence = kickoff_sequence(car_location)
            return self.active_sequence.tick(packet)

        # 3.  SMART POSITIONING: Detect game state and respond appropriately -----
        distance_to_ball = car_location.dist(ball_location)
        ball_velocity = Vec3(packet.game_ball.physics.velocity)
        
        # Detect current possession and game state
        has_possession = self._has_ball_possession(car_location, ball_location, ball_velocity)
        should_defend = self._should_prioritize_defense(packet, car_location, ball_location)
        
        target_location = ball_location
        state_label = "CHASE"
        
        if has_possession:
            # We control the ball - focus on maintaining possession or shooting
            shot_target = self._find_shot_toward_goal(packet, car_location, ball_location)
            if shot_target is not None:
                target_location = shot_target
                state_label = "DRIBBLE_SHOOT"
            else:
                # Keep ball close and look for opportunity
                target_location = self._get_dribble_target(car_location, ball_location, ball_velocity)
                state_label = "DRIBBLE"
        elif should_defend:
            # Ball is dangerous - rotate back or challenge strategically
            target_location = self._defensive_rotation_target(ball_location)
            state_label = "DEFEND"
        else:
            # Normal offense - try to get a good shot
            shot_target = self._find_shot_toward_goal(packet, car_location, ball_location)
            if shot_target is not None:
                target_location = shot_target
                state_label = "SHOOT"
            else:
                # No good shot - intercept smartly, don't just chase
                if distance_to_ball > 1200:
                    bp = self.get_ball_prediction_struct()
                    prediction_time = min(1.0, distance_to_ball / 1800.0)
                    future = find_slice_at_time(bp, packet.game_info.seconds_elapsed + prediction_time) if bp else None
                    if future is not None:
                        target_location = Vec3(future.physics.location)
                        state_label = "INTERCEPT"
                else:
                    # Close to ball but no good shot - position for next play
                    target_location = self._get_positioning_target(car_location, ball_location, ball_velocity)
                    state_label = "POSITION"
        
        # Defer to a teammate that already owns the play
        if state_label != "SHOOT" and self._teammate_has_priority(packet, car_location, ball_location):
            target_location = self._defensive_rotation_target(ball_location)
            state_label = "SUPPORT"

        # Boost detours favour small pads first, then full pads if we're desperate
        if state_label != "SHOOT":
            boost_target, boost_state = self._pick_boost_target(
                car_location=car_location,
                target_location=target_location,
                boost_amount=boost_amount,
                distance_to_ball=distance_to_ball,
            )
            if boost_target is not None:
                target_location = boost_target
                state_label = boost_state

        # --- Half-flip if facing completely the wrong way --------------------
        angle = angle_to_target(my_car, target_location)
        distance = car_location.dist(target_location)

        if (
            abs(angle) > 2.5
            and has_wheel_contact
            and car_speed < 600
            and distance > 1500
            and seconds - self._last_dodge_time > 2.5
        ):
            self.active_sequence = half_flip_sequence()
            self._last_dodge_time = seconds
            return self.active_sequence.tick(packet)

        # --- Dodge-to-accelerate (front flip for speed) ----------------------
        if self._should_dodge_to_accelerate(packet, my_car, car_location, target_location, car_speed):
            return self._begin_front_flip(packet)

        # 6.  Compute car controls --------------------------------------------
        controls = SimpleControllerState()
        controls.steer = steer_toward_target(my_car, target_location)

        target_speed = desired_speed_for_angle_and_distance(angle, distance)
        controls.throttle = throttle_to_reach_speed(car_speed, target_speed)

        controls.handbrake = should_use_handbrake(car_speed, angle)
        
        # Enhanced boost logic - different rules for different game states
        conserve_boost = state_label.startswith("BOOST") and boost_amount < 30.0
        is_dribbling = state_label in ["DRIBBLE", "DRIBBLE_SHOOT"]
        
        if is_dribbling:
            # Dribbling boost logic - more lenient for ball control
            controls.boost = self._should_boost_while_dribbling(
                car_speed, angle, distance_to_ball, boost_amount, has_wheel_contact
            )
        else:
            # Standard boost logic
            controls.boost = (
                not conserve_boost
                and controls.throttle > 0.9
                and not controls.handbrake
                and should_boost(
                    current_speed=car_speed,
                    angle=angle,
                    distance=distance,
                    has_wheel_contact=has_wheel_contact,
                    boost_amount=boost_amount,
                    target_speed=target_speed,
                )
            )

        # --- Debug rendering --------------------------------------------------
        self._draw_debug(car_location, car_velocity, target_location, state_label)

        return controls

    # ------------------------------------------------------------------
    # Offense helpers
    # ------------------------------------------------------------------

    def _find_shot_toward_goal(self, packet: GameTickPacket, car_location: Vec3, ball_location: Vec3):
        """
        Calculate where to drive to hit the ball toward the opponent goal.
        Returns None if no good shot is available.
        """
        # Vector from ball to opponent goal
        ball_to_goal = self.opponent_goal_location - ball_location
        if ball_to_goal.flat().length() < 100:
            return None  # Ball is basically in goal already
        
        # Target is BEHIND the ball (opposite side from goal)
        # So our hit pushes ball toward goal
        offset_distance = 130  # Distance behind ball to position ourselves
        target = ball_location - (ball_to_goal.flat().normalized() * offset_distance)
        
        # Only take this shot if we can reach it and it's a reasonable angle
        distance_to_target = car_location.flat().dist(target.flat())
        if distance_to_target > 3000:
            return None  # Too far, just chase ball instead
        
        # Check if this shot would actually send ball toward goal (angle check)
        car_to_ball = (ball_location - car_location).flat()
        if car_to_ball.length() > 50:
            angle_to_goal = car_to_ball.ang_to(ball_to_goal.flat())
            if angle_to_goal > 1.57:  # More than 90 degrees - bad angle
                return None
        
        return Vec3(target.x, target.y, 0)

    def _find_hittable_intercept(self, packet: GameTickPacket, car_location: Vec3):
        """
        Scan ball prediction for the earliest slice where the ball is at a
        hittable height (z < 300).  Return a target point offset so our hit
        sends the ball toward the opponent goal, or None.
        """
        ball_prediction = self.get_ball_prediction_struct()
        if ball_prediction is None or ball_prediction.num_slices < 2:
            return None

        now = packet.game_info.seconds_elapsed
        end_time = now + PREDICTION_SECONDS

        hittable_slice = find_matching_slice(
            ball_prediction, 0,
            lambda s: (
                s.game_seconds >= now + 0.1
                and s.game_seconds <= end_time
                and s.physics.location.z < HITTABLE_Z_THRESHOLD
            ),
            search_increment=6,
        )

        if hittable_slice is None:
            return None

        ball_pos = Vec3(hittable_slice.physics.location)

        # Offset the target so we approach from behind the ball relative to
        # the opponent goal.  This makes the contact push the ball goalward.
        goal_to_ball = (ball_pos - self.opponent_goal_location).flat()
        if goal_to_ball.length() < 1:
            goal_to_ball = Vec3(0, -1 if self.team == 0 else 1, 0)
        offset = goal_to_ball.normalized() * SHOT_OFFSET_DISTANCE

        intercept_target = ball_pos + offset
        # Make sure the target is on the ground
        intercept_target = Vec3(intercept_target.x, intercept_target.y, 0)

        # Sanity: only pursue if we can plausibly reach it in time
        time_to_reach = car_location.flat().dist(intercept_target.flat()) / max(car_location.flat().length(), 500)
        time_available = hittable_slice.game_seconds - now
        if time_to_reach > time_available * 1.5:
            return None

        return intercept_target

    def _predict_ball_fallback(self, packet: GameTickPacket, ball_location: Vec3, car_location: Vec3) -> Vec3:
        """
        When no hittable intercept is found, predict the ball 2 s ahead if we
        are far away; otherwise just aim at the ball.
        """
        if car_location.dist(ball_location) > 1500:
            bp = self.get_ball_prediction_struct()
            future = find_slice_at_time(bp, packet.game_info.seconds_elapsed + 2) if bp else None
            if future is not None:
                return Vec3(future.physics.location)
        return ball_location

    # ------------------------------------------------------------------
    # Defense helpers
    # ------------------------------------------------------------------

    def _ball_on_our_side(self, ball_location: Vec3) -> bool:
        """True when the ball is on our half of the field."""
        if self.team == 0:
            return ball_location.y < 0
        return ball_location.y > 0

    def _ball_behind_us(self, car_location: Vec3, ball_location: Vec3) -> bool:
        """True when the ball is closer to our goal than we are."""
        if self.team == 0:
            return ball_location.y < car_location.y
        return ball_location.y > car_location.y

    def _between_ball_and_own_goal(self, car_location: Vec3, ball_location: Vec3) -> bool:
        """True when the car is between the ball and our own goal."""
        if self.team == 0:
            return car_location.y < ball_location.y
        return car_location.y > ball_location.y

    def _defensive_rotation_target(self, ball_location: Vec3) -> Vec3:
        """
        Return a target point slightly in front of our goal, shifted toward the
        ball's x-position so we don't just park in the centre.
        """
        # A point 800 uu in front of the goal line, lerped toward ball x
        goal = self.own_goal_location
        offset_toward_ball = Vec3(ball_location.x * 0.5, 0, 0)
        inward = 800.0 if self.team == 0 else -800.0
        return Vec3(goal.x + offset_toward_ball.x, goal.y + inward, 0)

    # ------------------------------------------------------------------
    # Game state detection and smart positioning
    # ------------------------------------------------------------------
    
    def _has_ball_possession(self, car_location: Vec3, ball_location: Vec3, ball_velocity: Vec3) -> bool:
        """Detect if we have control/possession of the ball."""
        ball_distance = car_location.dist(ball_location)
        
        # Too far from ball
        if ball_distance > 200:
            return False
            
        # Ball is moving too fast to control
        ball_speed = ball_velocity.length()
        if ball_speed > 1200:
            return False
            
        # Ball is too high to dribble
        if ball_location.z > 150:
            return False
            
        return True
    
    def _should_prioritize_defense(self, packet: GameTickPacket, car_location: Vec3, ball_location: Vec3) -> bool:
        """Determine if we should focus on defense instead of offense."""
        # Ball is on our side of the field
        on_our_side = self._ball_on_our_side(ball_location)
        
        # Ball is behind us (closer to our goal than we are)
        behind_us = self._ball_behind_us(car_location, ball_location)
        
        # Check if opponents are closer to ball (immediate threat)
        my_distance = car_location.dist(ball_location)
        opponent_threat = False
        
        for idx, other in enumerate(packet.game_cars):
            if other.team == self.team or idx == self.index:
                continue
            if getattr(other, 'is_demolished', False):
                continue
                
            opponent_loc = Vec3(other.physics.location)
            opponent_distance = opponent_loc.dist(ball_location)
            
            # Opponent is significantly closer and ball is dangerous
            if opponent_distance < my_distance - 400 and on_our_side:
                opponent_threat = True
                break
        
        return (on_our_side and behind_us) or opponent_threat
    
    def _get_dribble_target(self, car_location: Vec3, ball_location: Vec3, ball_velocity: Vec3) -> Vec3:
        """Get target position for maintaining dribble control."""
        # Stay slightly behind and to the side of the ball
        to_goal = (self.opponent_goal_location - ball_location).flat().normalized()
        
        # Position ourselves to push the ball toward goal
        offset_distance = 120  # Stay close for control
        side_offset = 30  # Slightly to the side for better control
        
        target = ball_location - (to_goal * offset_distance)
        target.x += side_offset if ball_velocity.x > 0 else -side_offset
        
        return Vec3(target.x, target.y, 0)
    
    def _get_positioning_target(self, car_location: Vec3, ball_location: Vec3, ball_velocity: Vec3) -> Vec3:
        """Smart positioning to avoid ball chasing - predict where ball will be."""
        # Don't just chase current ball position - predict where it's going
        ball_speed = ball_velocity.flat().length()
        
        if ball_speed > 100:
            # Ball is moving - position to intercept
            time_prediction = 0.8  # Predict less far ahead for better positioning
            predicted_pos = ball_location + (ball_velocity * time_prediction)
            
            # Don't go too far from the play
            max_distance = 1500
            self_to_predicted = predicted_pos - car_location
            if self_to_predicted.length() > max_distance:
                predicted_pos = car_location + self_to_predicted.normalized() * max_distance
                
            return Vec3(predicted_pos.x, predicted_pos.y, 0)
        else:
            # Ball is stopped/slow - approach at an angle for a good hit
            to_goal = (self.opponent_goal_location - ball_location).flat().normalized()
            approach_distance = 200
            target = ball_location - (to_goal * approach_distance)
            return Vec3(target.x, target.y, 0)
    
    def _should_boost_while_dribbling(
        self, car_speed: float, angle: float, distance_to_ball: float, 
        boost_amount: float, has_wheel_contact: bool
    ) -> bool:
        """More lenient boost logic for dribbling situations."""
        if not has_wheel_contact or boost_amount <= 5:
            return False
            
        # Allow boosting with wider angle tolerance when dribbling
        if abs(angle) > 0.8:  # More lenient than normal (0.35)
            return False
            
        # Boost for dribbling control and speed
        if distance_to_ball < 250:  # Close to ball
            # Boost if we're going slow (need to keep up with ball)
            if car_speed < 800:
                return True
            # Or if we need a burst of speed to maintain control
            if car_speed < 1100 and boost_amount > 20:
                return True
                
        return False

    # ------------------------------------------------------------------
    # Team coordination & boost management
    # ------------------------------------------------------------------

    def _teammate_has_priority(self, packet: GameTickPacket, car_location: Vec3, ball_location: Vec3) -> bool:
        """Return True when a teammate is clearly closer to the play."""
        my_distance = car_location.dist(ball_location)
        give_way_margin = 350.0

        for idx, other in enumerate(packet.game_cars):
            if idx == self.index or other.team != self.team:
                continue
            if getattr(other, 'is_demolished', False):
                continue
            if not getattr(other, 'has_wheel_contact', True):
                continue

            teammate_loc = Vec3(other.physics.location)
            teammate_distance = teammate_loc.dist(ball_location)
            if teammate_distance + give_way_margin < my_distance:
                # Let the closer teammate go if they're not stuck behind the play.
                if not self._ball_behind_us(teammate_loc, ball_location):
                    return True

        return False

    def _pick_boost_target(
        self,
        car_location: Vec3,
        target_location: Vec3,
        boost_amount: float,
        distance_to_ball: float,
    ):
        """Decide whether to detour for boost, preferring small pads first."""
        urgent = boost_amount < 8.0
        if not urgent:
            if boost_amount >= 70.0:
                return None, None
            if distance_to_ball < 900.0:
                return None, None

        prefer_small = boost_amount < 35.0

        chosen_pad = None
        if prefer_small:
            chosen_pad = self._select_boost_pad(
                car_location=car_location,
                target_location=target_location,
                include_small=True,
                include_full=False,
                max_distance=1800.0,
                max_detour_angle=math.pi / 2,
            )

        if chosen_pad is None and (urgent or boost_amount < 50.0):
            chosen_pad = self._select_boost_pad(
                car_location=car_location,
                target_location=target_location,
                include_small=True,
                include_full=True,
                max_distance=2600.0,
                max_detour_angle=math.pi * 0.65,
            )

        if chosen_pad is None:
            return None, None

        state = "BOOST-SMALL" if not chosen_pad.is_full_boost else "BOOST-FULL"
        return chosen_pad.location, state

    def _select_boost_pad(
        self,
        car_location: Vec3,
        target_location: Vec3,
        include_small: bool,
        include_full: bool,
        max_distance: float,
        max_detour_angle: float,
    ):
        """Score pads by distance and alignment, returning the best match."""
        pads = getattr(self.boost_pad_tracker, 'boost_pads', [])
        if not pads:
            return None

        best_pad = None
        best_score = float('-inf')

        car_to_target = (target_location - car_location).flat()
        car_to_target_len = car_to_target.length()

        for pad in pads:
            if not pad.is_active:
                continue
            if pad.is_full_boost and not include_full:
                continue
            if (not pad.is_full_boost) and not include_small:
                continue

            pad_distance = car_location.dist(pad.location)
            if max_distance is not None and pad_distance > max_distance:
                continue

            car_to_pad = (pad.location - car_location).flat()
            pad_len = car_to_pad.length()
            if pad_len < 1.0:
                continue

            angle = 0.0
            if car_to_target_len > 20.0 and pad_len > 20.0:
                cos_angle = car_to_pad.dot(car_to_target) / (pad_len * car_to_target_len)
                cos_angle = max(-1.0, min(1.0, cos_angle))
                angle = math.acos(cos_angle)

            if angle > max_detour_angle:
                angle_score = -500.0 * (angle - max_detour_angle)
            else:
                angle_score = 400.0 * (1.0 - angle / max_detour_angle)

            distance_score = -pad_distance
            capacity_bonus = 260.0 if not pad.is_full_boost else 180.0
            score = angle_score + distance_score + capacity_bonus

            if score > best_score:
                best_score = score
                best_pad = pad

        return best_pad

    # ------------------------------------------------------------------
    # Dodge-to-accelerate
    # ------------------------------------------------------------------

    def _should_dodge_to_accelerate(
        self, packet: GameTickPacket, my_car,
        car_location: Vec3, target_location: Vec3, car_speed: float,
    ) -> bool:
        """Decides whether to do a forward dodge to gain speed on the ground."""
        seconds = float(packet.game_info.seconds_elapsed)
        if seconds - self._last_dodge_time < 1.2:
            return False

        has_wheel_contact = bool(getattr(my_car, 'has_wheel_contact', False))
        if not has_wheel_contact:
            return False
        if bool(getattr(my_car, 'jumped', False)) or bool(getattr(my_car, 'double_jumped', False)):
            return False

        angle = angle_to_target(my_car, target_location)
        if abs(angle) > 0.2:
            return False

        distance = car_location.dist(target_location)
        if distance < 1800.0:
            return False

        # Dodge for speed in a wider range
        if not (500.0 < car_speed < 1650.0):
            return False
        return True

    def _begin_front_flip(self, packet: GameTickPacket) -> SimpleControllerState:
        """Execute a front-flip sequence and return the first frame's controls."""
        self.active_sequence = Sequence([
            ControlStep(duration=0.05, controls=SimpleControllerState(jump=True)),
            ControlStep(duration=0.05, controls=SimpleControllerState(jump=False)),
            ControlStep(duration=0.2, controls=SimpleControllerState(jump=True, pitch=-1)),
            ControlStep(duration=0.8, controls=SimpleControllerState()),
        ])
        self._last_dodge_time = float(packet.game_info.seconds_elapsed)
        return self.active_sequence.tick(packet)

    # ------------------------------------------------------------------
    # Debug rendering
    # ------------------------------------------------------------------

    def _draw_debug(self, car_location: Vec3, car_velocity: Vec3, target: Vec3, label: str):
        """Render helpful debug lines and text."""
        self.renderer.draw_line_3d(car_location, target, self.renderer.white())
        self.renderer.draw_rect_3d(target, 8, 8, True, self.renderer.cyan(), centered=True)
        self.renderer.draw_string_3d(
            car_location, 1, 1,
            f'{label}  Spd:{car_velocity.length():.0f}',
            self.renderer.white(),
        )
