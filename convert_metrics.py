import argparse
import json
import pandas as pd
import os

def convert_jsonl_to_csv(jsonl_path, csv_path=None):
    """Convert a JSONL file to CSV format."""
    if not os.path.exists(jsonl_path):
        print(f"Error: File {jsonl_path} does not exist")
        return False
        
    try:
        # Read JSONL file
        data = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                data.append(json.loads(line))
        
        if not data:
            print(f"Warning: No data found in {jsonl_path}")
            return False
            
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Reorder columns to put timestamp first
        cols = df.columns.to_list()
        cols = cols[-1:] + cols[:-1]
        df = df[cols]
        
        # If no csv_path specified, use the same name as jsonl but with .csv extension
        if csv_path is None:
            csv_path = jsonl_path.replace('.jsonl', '.csv')
        
        # Save to CSV
        df.to_csv(csv_path, index=False)
        print(f"Successfully converted {jsonl_path} to {csv_path}")
        return True
        
    except Exception as e:
        print(f"Error converting file: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Convert vLLM metrics from JSONL to CSV format')
    parser.add_argument('--input', '-i', required=True, help='Input JSONL file path')
    parser.add_argument('--output', '-o', help='Output CSV file path (optional, defaults to input filename with .csv extension)')
    args = parser.parse_args()
    
    convert_jsonl_to_csv(args.input, args.output)

if __name__ == "__main__":
    main() 