import paramiko
import sys

host = "192.168.0.200"
username = "debian"
password = "magnus"

print(f"Attempting to connect to {host} as {username}...")

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # Try standard connect
    print("Trying standard connect...")
    client.connect(
        hostname=host,
        username=username,
        password=password,
        timeout=10,
        banner_timeout=30,
        look_for_keys=True,
        allow_agent=True
    )
    print("Standard connect success!")
    
    stdin, stdout, stderr = client.exec_command("echo hello")
    print(f"Output: {stdout.read().decode().strip()}")
    client.close()
    
except Exception as e:
    print(f"Standard connect failed: {e}")
    
    print("\nTrying explicit password only (no keys/agent)...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            username=username,
            password=password,
            timeout=10,
            look_for_keys=False,
            allow_agent=False
        )
        print("Explicit password connect success!")
        stdin, stdout, stderr = client.exec_command("echo hello")
        print(f"Output: {stdout.read().decode().strip()}")
        client.close()
    except Exception as e2:
        print(f"Explicit password connect failed: {e2}")

    print("\nTrying 'none' auth fallback manually...")
    try:
        t = paramiko.Transport((host, 22))
        t.start_client(timeout=10)
        t.auth_none(username)
        print("Auth none success!")
        # Validate session creation
        chan = t.open_session()
        chan.exec_command("echo hello")
        print("Channel exec success!")
        t.close()
    except Exception as e3:
        print(f"Auth none failed: {e3}")
