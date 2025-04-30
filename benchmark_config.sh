# Benchmark configuration parameters

# Request timeout in milliseconds
export GUIDELLM__REQUEST_TIMEOUT="6000"

# Maximum number of concurrent requests for throughput testing
export MAX_THROUGHPUT_RUN_CONCURRENCY=100

# Duration of each sweep test in seconds
export SWEEP_RUNTIME=100

# Scaling factor for served rate (1.2 means 20% above max)
export GUIDELLM__SCALE_FACTOR=1.2 

# Multiplier for throughput testing

export SWEEP_MULTIPLIERS="0.2 0.4 0.6 0.80.9 0.95 1.0"
