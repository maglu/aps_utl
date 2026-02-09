import paramiko
import logging
import sys

# Setup logging
logging.basicConfig()
logging.getLogger("paramiko").setLevel(logging.DEBUG)

def test_conn():
    host = "192.168.0.101"
    port = 1022
    username = "root"
    # We consciously set this to None to force Key/Agent auth
    password = None 
    
    print(f"Connecting to {host}:{port} as {username} (password={password})...")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=10,
            allow_agent=True,
            look_for_keys=True
        )
        print("SUCCESS: Connected!")
        stdin, stdout, stderr = client.exec_command("uptime")
        print(f"Output: {stdout.read().decode().strip()}")
        client.close()
    except Exception as e:
        print(f"FAILURE: {e}")

if __name__ == "__main__":
    test_conn()
