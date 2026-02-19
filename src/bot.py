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
from rlbot.messages.flat.QuickChatSelection import QuickChatSelection
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.ball_prediction_analysis import find_slice_at_time, find_matching_slice
from util.boost_pad_tracker import BoostPadTracker
from util.boost_utils import find_best_boost_pad, find_nearest_active_pad
from util.drive import (
    angle_to_target,
    desired_speed_for_angle_and_distance,
    get_speed_from_throttle,
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

        # 3.  GOAL-ORIENTED SHOOTING: Hit ball toward opponent goal -----------
        target_location = ball_location
        state_label = "CHASE"
        
        # Find where the ball will be and position to shoot at goal
        distance_to_ball = car_location.dist(ball_location)
        
        # Try to find a good shot opportunity
        shot_target = self._find_shot_toward_goal(packet, car_location, ball_location)
        if shot_target is not None:
            target_location = shot_target
            state_label = "SHOOT"
        else:
            # No good shot - just get to the ball quickly
            if distance_to_ball > 1200:
                bp = self.get_ball_prediction_struct()
                prediction_time = min(1.2, distance_to_ball / 1500.0)
                future = find_slice_at_time(bp, packet.game_info.seconds_elapsed + prediction_time) if bp else None
                if future is not None:
                    target_location = Vec3(future.physics.location)
                    state_label = "INTERCEPT"
        
        # Only get boost if critically low and not in a scoring position
        if boost_amount < 10 and distance_to_ball > 2500 and state_label != "SHOOT":
            pad = find_nearest_active_pad(self.boost_pad_tracker, car_location)
            if pad is not None and car_location.dist(pad.location) < 1500:
                target_location = pad.location
                state_label = "BOOST"

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
        controls.boost = (
            controls.throttle > 0.9
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
