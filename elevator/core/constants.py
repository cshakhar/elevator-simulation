DEFAULT_NUM_ELEVATORS = 3
DEFAULT_NUM_FLOORS = 60
DEFAULT_CAPACITY = 8
DEFAULT_ALGORITHM = "nearest_car"
ALGORITHMS = ["nearest_car", "round_robin", "zone_based"]

DEFAULT_INPUT_FILE = "data/sample_requests.csv"
DEFAULT_OUTPUT_POSITIONS = "output/elevator_positions.csv"
DEFAULT_OUTPUT_STATS = "output/passenger_stats.log"
DEFAULT_OUTPUT_METRICS = "output/metrics.csv"
DEFAULT_GENERATED_FILE = "data/generated_requests.csv"

CSV_COLUMNS = ["time", "id", "source", "dest"]

STOP_PICKUP = "pickup"
STOP_DROPOFF = "dropoff"

DEFAULT_START_FLOOR = 1

EXPRESS_LOBBY_FLOOR = 1
EXPRESS_SKIP_HIGH = 10

SIMULATION_LOGGER_NAME = "elevator.simulation"
