"""Warning delivery model for the research prototype.

Official-warning reception is probabilistic:
    P(receive) = device_ownership x awake_prob(time) x coverage
Social forwarding is handled by the interaction engine rather than this reception
model. The default probabilities are development assumptions, not verified external
estimates. Carr's YAML parameters were calibrated to the same survey channel margin,
so that margin cannot be reused as independent validation evidence.
"""

from __future__ import annotations

from ds.kernel.rng import stream_seed


def awake_prob(sim_minutes: int, day_start_min: int = 0) -> float:
    """Crude ATUS-style awake probability by local time-of-day.

    High during day, low overnight. This is a placeholder shape and must not be
    presented as an empirically estimated ATUS curve.
    """
    minute_of_day = (day_start_min + sim_minutes) % 1440
    hour = minute_of_day / 60.0
    if 7 <= hour < 22:
        return 0.95
    if 22 <= hour < 24 or 5 <= hour < 7:
        return 0.6
    return 0.15  # 0-5am deep night


class DeliveryModel:
    def __init__(self, device_ownership: float = 0.9, coverage: float = 0.85,
                 day_start_min: int = 8 * 60):
        self.device = device_ownership
        self.coverage = coverage
        self.day_start_min = day_start_min

    def receive_prob(self, sim_minutes: int) -> float:
        return self.device * awake_prob(sim_minutes, self.day_start_min) * self.coverage

    def delivers(self, agent_id: str, run_seed: int, step: int,
                 sim_minutes: int) -> bool:
        p = self.receive_prob(sim_minutes)
        r = stream_seed(
            run_seed,
            "warning_delivery",
            entity_id=agent_id,
            step=step,
        ) / (2**32)
        return r < p


class DeterministicDeliveryModel(DeliveryModel):
    """Deliver every covered warning in a controlled mechanism experiment."""

    def delivers(
        self,
        agent_id: str,
        run_seed: int,
        step: int,
        sim_minutes: int,
    ) -> bool:
        return True


class FixedProbabilityDeliveryModel(DeliveryModel):
    """Controlled Bernoulli warning delivery with a declared fixed probability."""

    def __init__(self, probability: float):
        if not 0.0 <= probability <= 1.0:
            raise ValueError("delivery probability must be within [0, 1]")
        self.probability = probability

    def receive_prob(self, sim_minutes: int) -> float:
        return self.probability

    def delivers(
        self,
        agent_id: str,
        run_seed: int,
        step: int,
        sim_minutes: int,
    ) -> bool:
        draw = stream_seed(
            run_seed,
            "warning_delivery",
            entity_id=agent_id,
            step=step,
        ) / (2**32)
        return draw < self.probability
