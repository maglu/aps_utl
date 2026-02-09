import json
import os
import sys

def load_config(config_path="config.json"):
    """
    Load configuration from a JSON file.
    
    Args:
        config_path (str): Path to the config file.
        
    Returns:
        dict: The configuration dictionary.
    """
    if not os.path.exists(config_path):
        print(f"Error: Configuration file '{config_path}' not found.")
        sys.exit(1)
        
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        # Basic validation
        # Basic validation
        # We don't enforce specific target names anymore (like 'aps' or 'bbb').
        # 'macros' is optional and handled safely by CLI.
        pass
                
        return config
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON configuration: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error loading config: {e}")
        sys.exit(1)
