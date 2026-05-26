# Default simulation parameters
DEFAULT_NUM_ELEVATORS = 3
DEFAULT_NUM_FLOORS = 60
DEFAULT_CAPACITY = 8
DEFAULT_ALGORITHM = "nearest_car"

# All supported scheduling algorithm names
ALGORITHMS = ["nearest_car", "round_robin", "zone_based"]

# Default file paths
DEFAULT_INPUT_FILE = "data/sample_requests.csv"
DEFAULT_OUTPUT_POSITIONS = "output/elevator_positions.csv"
DEFAULT_OUTPUT_STATS = "output/passenger_stats.log"
DEFAULT_GENERATED_FILE = "data/generated_requests.csv"

# CSV column names (input format and generated output)
CSV_COLUMNS = ["time", "id", "source", "dest"]

# Elevator stop slot names used in the stops dict
STOP_PICKUP = "pickup"
STOP_DROPOFF = "dropoff"

# Elevator physical defaults
DEFAULT_START_FLOOR = 1

# Express mode: last elevator skips floors between lobby and EXPRESS_SKIP_HIGH (inclusive)
EXPRESS_LOBBY_FLOOR = 1
EXPRESS_SKIP_HIGH = 10

# Logger name shared by schedulers that route through the simulation logger
SIMULATION_LOGGER_NAME = "elevator.simulation"
