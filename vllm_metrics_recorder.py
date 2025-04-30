import argparse
import requests
import os
import time
import datetime
import json
import pandas as pd
from requests.exceptions import RequestException
import sys

MAX_TEST_DURATION = int(os.environ.get("MAX_TEST_DURATION", 1200))
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def parse_metrics_response(raw_metrics_text : str, model_name : str):
    # The status_code must be validated before sending the raw text to this function
    metrics = {}
    for line in raw_metrics_text.splitlines():
        if line.startswith("#"):
            continue
        try:
            met_parts = line.split()
            met_name = met_parts[0].replace("vllm:", "").replace(",model_name="+model_name, "").replace("model_name="+model_name, "")
            metrics[met_name] = float(met_parts[1])
        except RuntimeError as e:
            print("Skipping parsing : " + line)
    
    return metrics

def convert_jsonl_to_csv(jsonl_path, csv_path):
    """Convert a JSONL file to CSV format."""
    # Read JSONL file
    data = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            data.append(json.loads(line))
    
    # Convert to DataFrame
    df = pd.DataFrame(data)
    
    # Reorder columns to put timestamp first
    cols = df.columns.to_list()
    cols = cols[-1:] + cols[:-1]
    df = df[cols]
    
    # Save to CSV
    df.to_csv(csv_path, index=False)
    print(f"Converted {jsonl_path} to {csv_path}")

def make_request_with_retry(url, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY):
    """Make a request with retry logic."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response
        except RequestException as e:
            if attempt < max_retries - 1:
                print(f"Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"All retry attempts failed. Last error: {str(e)}")
                raise

def main(host = "localhost", port = 8000, wait_until_ready = False, timeout = 60, interval = 2, dump_path = None):
    # Check if the vllm server is running
    # Make health endpoint check

    endpoint = "http://" + host + ":" + str(port)
    health_endpoint = endpoint + "/health"
    healthy = False

    if wait_until_ready:
        start_time = time.time()
        while not healthy:
            try:
                health_check_resp = make_request_with_retry(health_endpoint)
                if health_check_resp.status_code == 200:
                    healthy = True
            except RequestException:
                if time.time() - start_time > timeout:
                    raise TimeoutError("The vLLM instance has not yet come up. Exiting")
                time.sleep(1)
    else:
        try:
            make_request_with_retry(health_endpoint)
        except RequestException:
            raise RuntimeError("The vLLM instance is not reachable at : " + endpoint + ". Exiting")

    # Get model name
    try:
        models_resp = make_request_with_retry(endpoint + "/v1/models")
        model_name = models_resp.json()["data"][0]["id"]
    except (RequestException, KeyError, IndexError) as e:
        raise RuntimeError(f"Failed to get model information: {str(e)}")

    metrics_endpoint = endpoint + "/metrics"

    # Open file for continuous writing
    if dump_path:
        jsonl_path = dump_path if dump_path.endswith('.jsonl') else f"{dump_path}.jsonl"
        output_file = open(jsonl_path, 'w')
    else:
        output_file = None
        jsonl_path = None

    # vLLM server ready
    rec_start_time = time.time()
    consecutive_failures = 0
    
    try:
        while time.time() - rec_start_time < MAX_TEST_DURATION:
            try:
                time.sleep(interval)
                # Start running metrics requests
                current_timestamp = datetime.datetime.now()
                metrics_resp = make_request_with_retry(metrics_endpoint)
                metrics_dict = parse_metrics_response(metrics_resp.text, model_name=model_name)
                metrics_dict["timestamp"] = current_timestamp.isoformat()
                
                if output_file:
                    # Write each metrics entry as a JSON line
                    output_file.write(json.dumps(metrics_dict) + '\n')
                    output_file.flush()  # Ensure data is written to disk
                else:
                    print(json.dumps(metrics_dict))
                
                # Reset consecutive failures counter on successful request
                consecutive_failures = 0
                    
            except KeyboardInterrupt:
                print("\nReceived keyboard interrupt. Gracefully shutting down...")
                break
            except RequestException as e:
                consecutive_failures += 1
                print(f"Error collecting metrics (attempt {consecutive_failures}): {str(e)}")
                
                if consecutive_failures >= MAX_RETRIES:
                    print(f"Failed to collect metrics after {MAX_RETRIES} attempts. Exiting...")
                    break
                
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
    finally:
        if output_file:
            output_file.close()
            # Convert to CSV if we were writing to a file
            if jsonl_path:
                csv_path = jsonl_path.replace('.jsonl', '.csv')
                convert_jsonl_to_csv(jsonl_path, csv_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("HOST", "localhost"))
    parser.add_argument("--port", default=os.environ.get("PORT", 8000))
    parser.add_argument("--wait_until_ready", action="store_true")
    parser.add_argument("--timeout", default=os.environ.get("TIMEOUT", 60))
    parser.add_argument("--interval", default=os.environ.get("INTERVAL", 0.2), type=float)
    parser.add_argument("--dump_path", default=os.environ.get("DUMP_PATH", "metrics.jsonl"))
    args = parser.parse_args()
    main(
        host = args.host,
        port = args.port,
        wait_until_ready = args.wait_until_ready,
        timeout = args.timeout,
        interval = args.interval,
        dump_path = args.dump_path,
    )