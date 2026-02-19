"""
Kickoff routine for the Stealth bot.

Detects when a kickoff is happening and returns a Sequence of ControlSteps
that boost toward the ball and front-flip into it (simple diagonal flip kickoff).
"""

from rlbot.agents.base_agent import SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.sequence import Sequence, ControlStep
from util.vec import Vec3


# The ball spawns exactly at the origin during kickoff.
BALL_KICKOFF_ORIGIN = Vec3(0, 0, 0)
KICKOFF_BALL_THRESHOLD = 150.0  # Ball is "at origin" if within this distance


def is_kickoff(packet: GameTickPacket) -> bool:
    """
    Returns True when the game is in a kickoff state.
    We check two things:
      1. The game's is_kickoff_pause flag is set, OR
      2. The ball is very close to the origin and essentially stationary.
    """
    if packet.game_info.is_kickoff_pause:
        return True

    ball_loc = Vec3(packet.game_ball.physics.location)
    ball_vel = Vec3(packet.game_ball.physics.velocity)
    near_origin = ball_loc.flat().length() < KICKOFF_BALL_THRESHOLD
    nearly_still = ball_vel.length() < 50.0
    return near_origin and nearly_still


def kickoff_sequence(car_location: Vec3) -> Sequence:
    """
    Returns a Sequence that performs a simple speed-flip kickoff:
      1. Full throttle + boost toward the ball for a short time.
      2. Jump to start the dodge.
      3. Tilt forward and dodge (front-flip) into the ball.
      4. Recovery period.

    The timing is tuned for a typical diagonal spawn (~3500 uu from ball).
    """
    # Estimate how long to boost before flipping.
    dist_to_ball = car_location.flat().length()  # distance from origin on the ground

    # Longer boost phase when farther away; clamp between 0.4 s and 1.4 s.
    boost_duration = max(0.4, min(1.4, dist_to_ball / 3500.0))

    return Sequence([
        # Phase 1 – boost toward ball (steer is handled by the tick that starts the sequence)
        ControlStep(duration=boost_duration,
                    controls=SimpleControllerState(throttle=1.0, boost=True)),
        # Phase 2 – first jump
        ControlStep(duration=0.05,
                    controls=SimpleControllerState(jump=True, throttle=1.0, boost=True)),
        # Phase 3 – release jump (needed to allow a dodge)
        ControlStep(duration=0.05,
                    controls=SimpleControllerState(jump=False, throttle=1.0, boost=True)),
        # Phase 4 – dodge forward into the ball
        ControlStep(duration=0.20,
                    controls=SimpleControllerState(jump=True, pitch=-1, throttle=1.0)),
        # Phase 5 – let the dodge finish; coast forward
        ControlStep(duration=0.80,
                    controls=SimpleControllerState(throttle=1.0)),
    ])
