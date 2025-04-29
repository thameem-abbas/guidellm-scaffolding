import requests

def wait_until_vllm_ready(url: str, timeout: int = 300) -> None:
    """
    Wait until the VLLM server is ready to accept requests.

    Args:
        url (str): The URL of the VLLM server.
        timeout (int): The maximum time to wait in seconds. Default is 300
    """
    import time
    start_time = time.time()
    while True:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print("VLLM server is ready!")
                break
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to VLLM server: {e}")
        if time.time() - start_time > timeout:
            print("Timeout waiting for VLLM server to be ready.")
            break
        time.sleep(5)
    # Example usage
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Wait until VLLM server is ready.")
    parser.add_argument("--url", type=str, required=True, help="URL of the VLLM server")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    args = parser.parse_args()
    wait_until_vllm_ready(args.url, args.timeout)
# This script will wait until the VLLM server is ready to accept requests.
# It will check the server every 5 seconds and will timeout after the specified duration.
# The server is considered ready if it responds with a 200 status code.
