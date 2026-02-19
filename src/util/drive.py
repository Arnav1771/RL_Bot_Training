import math

from rlbot.utils.structures.game_data_struct import PlayerInfo

from util.orientation import Orientation, relative_location
from util.vec import Vec3


def limit_to_safe_range(value: float) -> float:
    """
    Controls like throttle, steer, pitch, yaw, and roll need to be in the range of -1 to 1.
    This will ensure your number is in that range. Something like 0.45 will stay as it is,
    but a value of -5.6 would be changed to -1.
    """
    if value < -1:
        return -1
    if value > 1:
        return 1
    return value


def steer_toward_target(car: PlayerInfo, target: Vec3) -> float:
    relative = relative_location(Vec3(car.physics.location), Orientation(car.physics.rotation), target)
    angle = math.atan2(relative.y, relative.x)
    return limit_to_safe_range(angle * 5)


def angle_to_target(car: PlayerInfo, target: Vec3) -> float:
    """Returns the 2D yaw angle (radians) from the car's forward direction to the target."""
    relative = relative_location(Vec3(car.physics.location), Orientation(car.physics.rotation), target)
    return math.atan2(relative.y, relative.x)


def throttle_to_reach_speed(current_speed: float, target_speed: float) -> float:
    """Simple proportional controller mapping speed error to throttle [-1, 1]."""
    # 500 uu/s of error corresponds to full throttle.
    return limit_to_safe_range((target_speed - current_speed) / 500.0)


def desired_speed_for_angle_and_distance(angle: float, distance: float) -> float:
    """Heuristic desired ground speed based on turn angle and target distance."""
    abs_angle = abs(angle)
    if abs_angle < 0.4:
        # Mostly lined up; go supersonic if target is not right in front
        return 2300.0 if distance > 600.0 else 1400.0
    if abs_angle < 1.2:
        # Medium turn; stay fast
        return 1600.0
    # Sharp turn; slow down but not too much
    return 900.0


def should_use_handbrake(current_speed: float, angle: float) -> bool:
    """Returns True when a powerslide turn is likely beneficial."""
    return abs(angle) > 1.55 and current_speed > 800.0


def should_boost(
    current_speed: float,
    angle: float,
    distance: float,
    has_wheel_contact: bool,
    boost_amount: float,
    target_speed: float,
) -> bool:
    """Aggressive boost usage: boost when lined up and we need more speed."""
    if not has_wheel_contact:
        return False
    if boost_amount <= 1.0:
        return False
    # More lenient angle threshold
    if abs(angle) > 0.6:
        return False
    # Boost if we're trying to go fast and below target speed
    if target_speed >= 1400.0 and current_speed < target_speed - 100:
        return True
    return False


# ---------------------------------------------------------------------------
# Additional helpers
# ---------------------------------------------------------------------------

def get_speed_from_throttle(boosting: bool = False) -> float:
    """
    Returns the approximate maximum ground speed (uu/s) the car can reach.
      - throttle only (no boost): ~1410 uu/s
      - with boost:               ~2300 uu/s (supersonic)
    """
    return 2300.0 if boosting else 1410.0


def half_flip_sequence() -> 'Sequence':
    """
    Returns a Sequence that performs a half-flip.

    A half-flip is useful when the car is facing away from its target:
      1. Back-flip (jump, tilt back, dodge backwards).
      2. Immediately cancel the flip by pushing forward on the stick.
      3. Air-roll 180° so the car lands facing the new direction.
    """
    from rlbot.agents.base_agent import SimpleControllerState
    from util.sequence import Sequence, ControlStep

    return Sequence([
        # Throttle backwards briefly to set up
        ControlStep(duration=0.10,
                    controls=SimpleControllerState(throttle=-1.0)),
        # First jump
        ControlStep(duration=0.05,
                    controls=SimpleControllerState(jump=True, throttle=-1.0)),
        # Release jump
        ControlStep(duration=0.05,
                    controls=SimpleControllerState(jump=False, throttle=-1.0)),
        # Back-flip dodge
        ControlStep(duration=0.10,
                    controls=SimpleControllerState(jump=True, pitch=1)),
        # Cancel the flip by pitching forward + air-roll to rotate 180°
        ControlStep(duration=0.45,
                    controls=SimpleControllerState(pitch=-1, roll=1)),
        # Let the car settle / land
        ControlStep(duration=0.55,
                    controls=SimpleControllerState(throttle=1.0)),
    ])
