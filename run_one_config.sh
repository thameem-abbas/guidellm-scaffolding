# Parameters needed
# 1. Model Path
# 2. TP Level
# 3. OUTPUT_DIR
# 4. KV_CACHE_PRECISION (optional)
# 5. SWEEP_MODE (optional, "multiplier" or "absolute", defaults to "multiplier")

MODEL_NAME=$1
TENSOR_PARALLEL_SIZE=$2
OUTPUT_DIR=$3

# Handle optional parameters
if [ "$4" = "multiplier" ] || [ "$4" = "absolute" ]; then
    # If 4th parameter is a sweep mode, it means KV_CACHE_PRECISION was not provided
    SWEEP_MODE=$4
    KV_CACHE_PRECISION=""
else
    # 4th parameter is KV_CACHE_PRECISION
    KV_CACHE_PRECISION=$4
    # 5th parameter is SWEEP_MODE if provided, otherwise default to "multiplier"
    SWEEP_MODE=${5:-"multiplier"}
fi

# Check if VLLM_BENCHMARK_HOME is set
if [ -z "$VLLM_BENCHMARK_HOME" ]; then
    echo "Error: VLLM_BENCHMARK_HOME environment variable is not set"
    echo "Please set it to the directory containing the VLLM benchmark code"
    exit 1
fi

# Check if VLLM binary is available
if ! command -v vllm &> /dev/null; then
    echo "Error: VLLM binary not found in PATH"
    echo "Please ensure VLLM is installed and available in your PATH"
    exit 1
fi

# Source the benchmark configuration
if [ -f "benchmark_config.sh" ]; then
    source benchmark_config.sh
else
    echo "Error: benchmark_config.sh not found"
    exit 1
fi

# ENV required
# 1. VLLM BENCHMARK HOME to cd into and save the current directory to be changed back to
# 2. Scaling factor for served rate to be set to 1.2 to start and then be adjusted from there.

# Check if the last serve pid file exists
if [ -f "$OUTPUT_DIR/serve.pid" ]; then
    SERVE_PID=$(cat $OUTPUT_DIR/serve.pid)
    if ps -p $SERVE_PID > /dev/null; then
        echo "VLLM server is already running with PID: $SERVE_PID"
        exit 1
    else
        echo "VLLM server is not running. Starting a new instance."
    fi
fi

# Save the current directory
CURRENT_DIR=$(pwd)
cd $VLLM_BENCHMARK_HOME

export GUIDELLM__REQUEST_TIMEOUT="6000"

MAX_THROUGHPUT_RUN_CONCURRENCY=100

# Set the scaling factor to 1.2
export GUIDELLM__SCALE_FACTOR=1.2

SWEEP_RUNTIME=100

# Create a folder with the output name if it doesn't exist
mkdir -p $OUTPUT_DIR

# Start the VLLM server
if [ -z "$KV_CACHE_PRECISION" ]; then
    echo "Running without KV cache precision"
    nohup vllm serve \
    $MODEL_NAME \
    --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
    --port 8000 \
    --no-enable-prefix-caching \
    --load-format dummy \
    --max-model-len 8192 > $OUTPUT_DIR/serve.log 2>&1 &
else
    echo "Running with KV cache precision: $KV_CACHE_PRECISION"
    nohup vllm serve \
    $MODEL_NAME \
    --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
    --port 8000 \
    --no-enable-prefix-caching \
    --kv-cache-dtype $KV_CACHE_PRECISION \
    --load-format dummy \
    --max-model-len 8192 > $OUTPUT_DIR/serve.log 2>&1 &
fi
# Save the PID of the last background process
SERVE_PID=$!
echo "VLLM server started with PID: $SERVE_PID"
# Save the PID to a file
echo $SERVE_PID > $OUTPUT_DIR/serve.pid

# Wait for the server to start
python3 $CURRENT_DIR/wait_until_vllm_ready.py --url http://localhost:8000/health --timeout 600
if [ $? -ne 0 ]; then
    echo "VLLM server did not start in time. Exiting."
    # Kill the server process
    kill -2 $SERVE_PID
    # Check if the process is still running
    if ps -p $SERVE_PID > /dev/null; then
        echo "Killing VLLM server with PID: $SERVE_PID"
        kill -9 $SERVE_PID
    fi
    # Exit
    exit 1
fi

# Start the metrics recorder in the background and save the PID and log file
echo "Starting VLLM metrics recorder..."
python3 $CURRENT_DIR/vllm_metrics_recorder.py \
    --host localhost \
    --port 8000 \
    --wait_until_ready \
    --interval 0.2 \
    --dump_path $OUTPUT_DIR/vllm_metrics.csv > $OUTPUT_DIR/vllm_metrics_throughput.log 2>&1 &
METRICS_RECORDER_PID=$!
echo "Metrics recorder started with PID: $METRICS_RECORDER_PID"

# Run an overload test with benchmark_serving.py
python3 benchmark_serving.py \
    --backend vllm \
    --model $MODEL_NAME \
    --endpoint /v1/completions \
    --dataset-name random \
    --random-input-len 512 \
    --random-output-len 2048 \
    --num-prompts $MAX_THROUGHPUT_RUN_CONCURRENCY \
    --ignore-eos \
    --seed 42 > $OUTPUT_DIR/benchmark_report_serving_max.txt
echo "Benchmark report saved to $OUTPUT_DIR/benchmark_report_serving_max.txt"

# Kill the metrics recorder
echo "Stopping metrics recorder..."
kill -2 $METRICS_RECORDER_PID
sleep 5
if ps -p $METRICS_RECORDER_PID > /dev/null; then
    echo "Killing metrics recorder with PID: $METRICS_RECORDER_PID"
    kill -9 $METRICS_RECORDER_PID
fi

# Parse the report to get the served request rate.
# Max request rate for guidellm is to be 1.2x of the max request rate we get out of the benchmark.
# This is due to the the intended request rate being 1.2x of the served request rate.
# This is empirical and cannot be a sustained way of doing things.

served_req_rate=$(python3 $CURRENT_DIR/parse_serving_report.py --report $OUTPUT_DIR/benchmark_report_serving_max.txt --only-req-rate)
echo "GUIDELLM intended request rate: $served_req_rate"

# Calculate the max request rate using awk
# Max test request rate is GUIDELLM__SCALE_FACTOR * served_req_rate
MAX_REQUEST_RATE=$(awk -v x="$served_req_rate" 'BEGIN { y = 1.2; print (x * y) }')
echo "Max request rate: $MAX_REQUEST_RATE"

# Define sweep points based on mode
if [ "$SWEEP_MODE" = "absolute" ]; then
    # Absolute mode: Calculate actual rates directly
    SWEEP=$(awk -v x="$MAX_REQUEST_RATE" 'BEGIN { for (i=0.2; i<=1; i+=0.2) print i * x }')
    echo "Using absolute sweep mode with rates: $SWEEP"
else
    # Multiplier mode: Use multipliers and calculate rates in the loop
    # Check if SWEEP_MULTIPLIERS is set in environment, otherwise use default
    if [ -z "$SWEEP_MULTIPLIERS" ]; then
        SWEEP=(0.2 0.4 0.6 0.8 0.9 0.95 1.0)
    else
        # Convert space-separated string to array
        IFS=' ' read -r -a SWEEP <<< "$SWEEP_MULTIPLIERS"
    fi
    echo "Using multiplier sweep mode with multipliers: ${SWEEP[@]}"
fi

# Run the benchmark test with the specified parameters
if [ "$SWEEP_MODE" = "absolute" ]; then
    # Absolute mode: Use rates directly
    for rate in $SWEEP
    do
        echo "Running test with request rate: $rate"
        
        # Start the metrics recorder for this test
        echo "Starting VLLM metrics recorder for rate $rate..."
        python3 $CURRENT_DIR/vllm_metrics_recorder.py \
            --host localhost \
            --port 8000 \
            --wait_until_ready \
            --interval 0.2 \
            --dump_path $OUTPUT_DIR/vllm_metrics_${rate}.csv | tee $OUTPUT_DIR/vllm_metrics_${rate}.log 2>&1 &
        METRICS_RECORDER_PID=$!
        echo "Metrics recorder started with PID: $METRICS_RECORDER_PID"
        
        # Run the benchmark test with the specified parameters
        guidellm benchmark --target 'http://localhost:8000' \
                 --model $MODEL_NAME \
                 --processor $MODEL_NAME \
                 --data='{"prompt_tokens":512 ,"prompt_tokens_stdev":128,"prompt_tokens_min":256,"prompt_tokens_max":1024,"output_tokens":2048, "output_tokens_stdev":512,"output_tokens_min":1024,"output_tokens_max":3072}'  \
                 --rate-type constant \
                 --max-seconds $SWEEP_RUNTIME \
                 --output-path $OUTPUT_DIR/benchmark_report_serving_$rate.json \
                 --rate $rate
        echo "Benchmark report saved to $OUTPUT_DIR/benchmark_report_serving_$rate.json"
        
        # Stop the metrics recorder
        echo "Stopping metrics recorder for rate $rate..."
        kill -2 $METRICS_RECORDER_PID
        sleep 5
        if ps -p $METRICS_RECORDER_PID > /dev/null; then
            echo "Killing metrics recorder with PID: $METRICS_RECORDER_PID"
            kill -9 $METRICS_RECORDER_PID
        fi
        
        # Wait for 30 seconds to ensure system is clear of previous test effects
        echo "Waiting 30 seconds before next test..."
        sleep 30
    done
else
    # Multiplier mode: Calculate rates from multipliers
    for i in ${SWEEP[@]}
    do
        # Calculate the actual rate for this sweep point
        ACTUAL_RATE=$(awk -v x="$MAX_REQUEST_RATE" -v y="$i" 'BEGIN { print (x * y) }')
        echo "Running test with request rate multiplier: $i (actual rate: $ACTUAL_RATE)"
        
        # Start the metrics recorder for this test
        echo "Starting VLLM metrics recorder for multiplier $i..."
        python3 $CURRENT_DIR/vllm_metrics_recorder.py \
            --host localhost \
            --port 8000 \
            --wait_until_ready \
            --interval 0.2 \
            --dump_path $OUTPUT_DIR/vllm_metrics_${i}.csv > $OUTPUT_DIR/vllm_metrics_${i}.log 2>&1 &
        METRICS_RECORDER_PID=$!
        echo "Metrics recorder started with PID: $METRICS_RECORDER_PID"
        
        # Run the benchmark test with the specified parameters
        guidellm benchmark --target 'http://localhost:8000' \
                 --model $MODEL_NAME \
                 --processor $MODEL_NAME \
                 --data='{"prompt_tokens":512 ,"prompt_tokens_stdev":128,"prompt_tokens_min":256,"prompt_tokens_max":1024,"output_tokens":2048, "output_tokens_stdev":512,"output_tokens_min":1024,"output_tokens_max":3072}'  \
                 --rate-type constant \
                 --max-seconds $SWEEP_RUNTIME \
                 --output-path $OUTPUT_DIR/benchmark_report_serving_$i.json \
                 --rate $ACTUAL_RATE
        echo "Benchmark report saved to $OUTPUT_DIR/benchmark_report_serving_$i.json"
        
        # Stop the metrics recorder
        echo "Stopping metrics recorder for multiplier $i..."
        kill -2 $METRICS_RECORDER_PID
        sleep 5
        if ps -p $METRICS_RECORDER_PID > /dev/null; then
            echo "Killing metrics recorder with PID: $METRICS_RECORDER_PID"
            kill -9 $METRICS_RECORDER_PID
        fi
        
        # Wait for 30 seconds to ensure system is clear of previous test effects
        echo "Waiting 30 seconds before next test..."
        sleep 30
    done
fi

# Kill the server process
kill -2 $SERVE_PID
sleep 60
# Check if the process is still running
if ps -p $SERVE_PID > /dev/null; then
    echo "Killing VLLM server with PID: $SERVE_PID"
    kill -9 $SERVE_PID
fi

# Wait for 60 seconds to ensure the process is terminated
wait $SERVE_PID 2>/dev/null
sleep 60

# cd back to the original directory
cd $CURRENT_DIR