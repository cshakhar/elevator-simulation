import logging

from elevator.core.constants import SIMULATION_LOGGER_NAME

logger = logging.getLogger(SIMULATION_LOGGER_NAME)


def create_scheduler(algorithm: str, elevators, num_floors: int):
    from algorithms.nearest_car import NearestCarScheduler
    from algorithms.round_robin import RoundRobinScheduler
    from algorithms.zone_based import ZoneBasedScheduler

    mapping = {
        "nearest_car": NearestCarScheduler,
        "round_robin": RoundRobinScheduler,
        "zone_based": ZoneBasedScheduler,
    }
    if algorithm not in mapping:
        raise ValueError(
            f"Unknown algorithm {algorithm!r}. "
            f"Choose from: {list(mapping)}"
        )
    if algorithm == "zone_based":
        if any(e.express_floors is not None for e in elevators):
            logger.warning(
                "Combining 'zone_based' algorithm with express_config may cause "
                "passengers to be unroutable if zone and express boundaries conflict."
            )
        return ZoneBasedScheduler(elevators, num_floors)
    return mapping[algorithm](elevators)
