import json
import os
import sys

def load_config(config_name="aps_config.json"):
    """
    Load configuration from a JSON file.
    
    Args:
        config_name (str): Name of the config file.
        
    Returns:
        dict: The configuration dictionary.
    """
    cwd_path = os.path.join(os.getcwd(), config_name)
    tool_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tool_path = os.path.join(tool_dir, config_name)
    
    if os.path.exists(cwd_path):
        config_path = cwd_path
    elif os.path.exists(tool_path):
        config_path = tool_path
    else:
        print(f"Error: Configuration file '{config_name}' not found in current directory ({os.getcwd()}) or tool directory ({tool_dir}).")
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
