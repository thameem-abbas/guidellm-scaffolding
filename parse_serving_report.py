def parse_report(report_string):
    """
    Example :
        INFO 03-20 19:01:50 [__init__.py:256] Automatically detected platform cuda.
        Namespace(backend='vllm', base_url=None, host='127.0.0.1', port=8000, endpoint='/v1/completions', dataset_name='random', dataset_path=None, max_concurrency=None, model='meta-llama/Llama-3.2-3B', tokenizer=None, use_beam_search=False, num_prompts=100, logprobs=None, request_rate=inf, burstiness=1.0, seed=0, trust_remote_code=False, disable_tqdm=False, profile=False, save_result=False, save_detailed=False, metadata=None, result_dir=None, result_filename=None, ignore_eos=False, percentile_metrics='ttft,tpot,itl', metric_percentiles='99', goodput=None, sonnet_input_len=550, sonnet_output_len=150, sonnet_prefix_len=200, sharegpt_output_len=None, random_input_len=512, random_output_len=2048, random_range_ratio=1.0, random_prefix_len=0, hf_subset=None, hf_split=None, hf_output_len=None, tokenizer_mode='auto', served_model_name=None, lora_modules=None)
        Starting initial single prompt test run...
        Initial test run completed. Starting main benchmark run...
        Traffic request rate: inf
        Burstiness factor: 1.0 (Poisson process)
        Maximum request concurrency: None
        ============ Serving Benchmark Result ============
        Successful requests:                     100       
        Benchmark duration (s):                  119.66    
        Total input tokens:                      51200     
        Total generated tokens:                  204800    
        Request throughput (req/s):              0.84      
        Output token throughput (tok/s):         1711.49   
        Total Token throughput (tok/s):          2139.36   
        ---------------Time to First Token----------------
        Mean TTFT (ms):                          1809.75   
        Median TTFT (ms):                        1748.44   
        P99 TTFT (ms):                           3568.84   
        -----Time per Output Token (excl. 1st token)------
        Mean TPOT (ms):                          40.83     
        Median TPOT (ms):                        42.40     
        P99 TPOT (ms):                           56.37     
        ---------------Inter-token Latency----------------
        Mean ITL (ms):                           40.83     
        Median ITL (ms):                         26.02     
        P99 ITL (ms):                            157.07    
        ==================================================
    """
    # Split the report string into lines
    lines = report_string.strip().split('\n')
    metrics = {}

    # Iterate through each line and extract relevant information
    skip_terms = [
        "INFO", 
        "Namespace", 
        "Starting initial single prompt test run", 
        "Initial test run completed", 
        "Starting main benchmark run", 
        "Traffic request rate", 
        "Burstiness factor", 
        "Maximum request concurrency"
    ]
    for line in lines:
        # Skip lines that contain any of the skip terms
        if any(term in line for term in skip_terms):
            continue

        # Check if the line contains a metric
        if "Successful requests" in line:
            metrics["successful_requests"] = int(line.split(":")[1].strip())
        elif "Benchmark duration" in line:
            metrics["benchmark_duration"] = float(line.split(":")[1].strip())
        elif "Total input tokens" in line:
            metrics["total_input_tokens"] = int(line.split(":")[1].strip())
        elif "Total generated tokens" in line:
            metrics["total_generated_tokens"] = int(line.split(":")[1].strip())
        elif "Request throughput" in line:
            metrics["request_throughput"] = float(line.split(":")[1].strip())
        elif "Output token throughput" in line:
            metrics["output_token_throughput"] = float(line.split(":")[1].strip())
        elif "Total Token throughput" in line:
            metrics["total_token_throughput"] = float(line.split(":")[1].strip())
        elif "Mean TTFT" in line:
            metrics["mean_ttft"] = float(line.split(":")[1].strip())
        elif "Median TTFT" in line:
            metrics["median_ttft"] = float(line.split(":")[1].strip())
        elif "P99 TTFT" in line:
            metrics["p99_ttft"] = float(line.split(":")[1].strip())
        elif "Mean TPOT" in line:
            metrics["mean_tpot"] = float(line.split(":")[1].strip())
        elif "Median TPOT" in line:
            metrics["median_tpot"] = float(line.split(":")[1].strip())
        elif "P99 TPOT" in line:
            metrics["p99_tpot"] = float(line.split(":")[1].strip())
        elif "Mean ITL" in line:
            metrics["mean_itl"] = float(line.split(":")[1].strip())
        elif "Median ITL" in line:
            metrics["median_itl"] = float(line.split(":")[1].strip())
        elif "P99 ITL" in line:
            metrics["p99_itl"] = float(line.split(":")[1].strip())
        elif "==================================================" in line:
            # End of the report
            break
    return metrics

def main():
    import argparse

    # Example report string
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=str, help="Path to the report file")
    parser.add_argument("--only-req-rate", action="store_true", help="Only print the request rate")
    args = parser.parse_args()
    report_path = args.report
    with open(report_path, "r") as f:
        report_string = f.read()
    # Parse the report
    metrics = parse_report(report_string)
    # Print the parsed metrics
    if args.only_req_rate:
        print(metrics['request_throughput'])
        return
    print("Parsed Metrics:")
    for key, value in metrics.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    main()