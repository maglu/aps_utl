import paramiko
import time
from .communicator import Communicator

class BBBConnection(Communicator):
    def __init__(self, host, username, password, uart_port, baudrate, uart_login=None, uart_password=None, verbose=False):
        self.host = host
        self.username = username
        self.password = password
        self.uart_port = uart_port
        self.baudrate = baudrate
        self.uart_login = uart_login
        self.uart_password = uart_password
        self.verbose = verbose
        self.client = None
        self.shell = None

    def log(self, msg):
        if self.verbose:
            print(msg)

    def connect(self):
        try:
            self.client = paramiko.SSHClient()
            # StrictHostKeyChecking=no equivalent
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.log(f"Connecting to BBB at {self.host}...")
            try:
                self.client.connect(
                    hostname=self.host,
                    username=self.username,
                    password=self.password if self.password else None,
                    timeout=10,
                    banner_timeout=30
                )
            except paramiko.SSHException as e:
                # Fallback for "No existing session" or partial auth failures
                if "No existing session" in str(e) and self.password:
                    self.log(f"Connection failed ({e}), retrying with explicit password (no keys)...")
                    self.client.connect(
                        hostname=self.host,
                        username=self.username,
                        password=self.password,
                        timeout=10,
                        banner_timeout=30,
                        look_for_keys=False,
                        allow_agent=False
                    )
                else:
                    raise e
        except paramiko.AuthenticationException:
            self.log("Authentication failed. Trying 'none' authentication method...")
            try:
                t = paramiko.Transport((self.host, 22)) # Default SSH port for BBB
                t.start_client(timeout=10)
                try:
                    t.auth_none(self.username)
                    self.client = paramiko.SSHClient()
                    self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    self.client._transport = t
                    self.log("Connected to BBB via 'none' authentication.")
                except Exception as e:
                     t.close()
                     raise e
            except Exception as e:
                raise ConnectionError(f"Failed to connect to BBB (including 'none'): {e}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to BBB: {e}")

        try:
            # Setup UART on BBB
            setup_cmd = f"stty -F {self.uart_port} {self.baudrate} raw -echo"
            stdin, stdout, stderr = self.client.exec_command(setup_cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                err = stderr.read().decode()
                self.log(f"Warning: Failed to configure UART with stty: {err}")
                # We proceed anyway, maybe it's already configured or using a different tool?
            
            self.log("BBB SSH Connection established. UART configured (best effort).")
            
        except Exception as e:
            raise ConnectionError(f"Failed to connect to BBB: {e}")

    def disconnect(self):
        if self.client:
            self.client.close()
            self.log("BBB Connection closed.")

    def _log_rx(self, msg):
        if self.verbose and msg:
            # Handle multi-line output nicely?
            # Or just print raw? User asked for "< ...".
            # Let's clean it up slightly but keep structure.
            clean_msg = msg.strip()
            if clean_msg:
                print(f"< {clean_msg}")

    def _log_tx(self, msg):
        if self.verbose:
            print(f"> {msg}")

    def send_command(self, cmd: str) -> str:
        """
        Send command via BBB UART.
        Strategy: Start reading, send Enter, check for login, then send command.
        """
        if not self.client:
            raise ConnectionError("Not connected.")

        try:
            # --- OPTIMIZATION: Fast Path Check ---
            # Check if we are already at a prompt
            is_logged_in = False
            
            # Quick probe (0.5s)
            probe_read_cmd = f"timeout 0.5 cat {self.uart_port}"
            p_in, p_out, p_err = self.client.exec_command(probe_read_cmd)
            time.sleep(0.1) 
            self.client.exec_command(f"echo -e '\\n' > {self.uart_port}")
            
            probe_output = p_out.read().decode().strip()
            
            # Check for prompt
            if "#" in probe_output or "$" in probe_output:
                self.log("Fast path: Prompt detected. Skipping login.")
                is_logged_in = True
            
            # --- Slow Path: Login/Password ---
            if not is_logged_in:
                if self.uart_login or self.uart_password:
                     self.log("--- Login Check ---")
                     
                     # Start a longer probe
                     probe_read_cmd = f"timeout 3 cat {self.uart_port}"
                     p_in, p_out, p_err = self.client.exec_command(probe_read_cmd)
                     time.sleep(0.5) # Wait for cat to start
                     
                     # Send newline to trigger prompt refresh
                     self._log_tx("(\\n) [Checking for prompt]")
                     self.client.exec_command(f"echo -e '\\n' > {self.uart_port}")
                     
                     # Wait for output to accumulate
                     probe_output = p_out.read().decode().strip()
                     self._log_rx(probe_output)
                     
                     # Handle Login
                     if "login:" in probe_output.lower():
                         self._log_tx(self.uart_login)
                         self.client.exec_command(f"echo -e '{self.uart_login}\\n' > {self.uart_port}")
                         time.sleep(1.0) # Wait for login to process
                         # Assume we might need password next (probe again or implicit)
                         probe_output += " password: " 
    
                     # Handle Password
                     # Note: We re-probe if we just sent login? 
                     # The previous probe output is stale if we just sent login.
                     # Let's peek again quickly if we suspect password challenge.
                     if self.uart_password is not None:
                         # If we just sent login, we need to read the RESULT of that login
                         if "login:" in probe_output.lower(): # Meaning we acted on it
                             pw_read_cmd = f"timeout 1 cat {self.uart_port}"
                             pw_in, pw_out, pw_err = self.client.exec_command(pw_read_cmd)
                             pw_output = pw_out.read().decode().strip()
                             self._log_rx(pw_output)
                             
                             if "password:" in pw_output.lower():
                                 self._log_tx(self.uart_password if self.uart_password else "(empty)")
                                 pw_to_send = self.uart_password
                                 self.client.exec_command(f"echo -e '{pw_to_send}\\n' > {self.uart_port}")
                                 time.sleep(1.0)
                         elif "password:" in probe_output.lower():
                             # Initial probe already showed password (unlikely without login, but possible)
                             self._log_tx(self.uart_password if self.uart_password else "(empty)")
                             pw_to_send = self.uart_password
                             self.client.exec_command(f"echo -e '{pw_to_send}\\n' > {self.uart_port}")
                             time.sleep(1.0)
                                 
                     # 3. Wait for Shell Prompt
                     # After login/password, we expect a shell prompt (# or $)
                     self.log("Waiting for shell prompt...")
                     max_retries = 3
                     for i in range(max_retries):
                         prompt_read_cmd = f"timeout 2 cat {self.uart_port}"
                         pr_in, pr_out, pr_err = self.client.exec_command(prompt_read_cmd)
                         # Maybe send a newline to provoke a prompt?
                         if i > 0:
                             self.client.exec_command(f"echo -e '\\n' > {self.uart_port}")
                         
                         pr_output = pr_out.read().decode().strip()
                         self._log_rx(pr_output)
                         
                         if "#" in pr_output or "$" in pr_output:
                             self.log("Shell prompt detected.")
                             break
                         else:
                             self.log(f"Prompt not detected yet (attempt {i+1}/{max_retries})...")
                             time.sleep(1.0)

            # 4. Now perform the actual command execution
            self.log("--- Command Execution ---")
            # Restart reader for the actual command
            # self.log(f"Starting command read on {self.uart_port}...")
            read_cmd = f"timeout 3 cat {self.uart_port}" 
            stdin_r, stdout_r, stderr_r = self.client.exec_command(read_cmd)
            time.sleep(0.2)
            
            self._log_tx(cmd)
            full_cmd = f"echo -e '{cmd}\\n' > {self.uart_port}"
            self.client.exec_command(full_cmd)
            
            # self.log("Waiting for UART response...")
            out = stdout_r.read().decode().strip()
            self._log_rx(out)
            
            return self._clean_response(out, cmd)
            
        except Exception as e:
            return f"Error communicating via UART: {e}"

    def _clean_response(self, output: str, cmd: str) -> str:
        """
        Remove command echo and trailing prompts from output.
        """
        lines = output.splitlines()
        if not lines:
            return output
            
        # 1. Remove Echo (First line usually matches command)
        # We strip both to be safe
        if lines[0].strip() == cmd.strip():
            lines.pop(0)
            
        # 2. Remove Trailing Prompts
        # Prompts usually look like "root@APS...:~#" or contain "#" / "$" at the end
        # We'll remove trailing lines that look like prompts.
        # We iterate from the end.
        while lines:
            last = lines[-1].strip()
            
            # Remove empty lines
            if not last:
                lines.pop()
                continue
                
            # Heuristic: Ends with # or $ and optionally has username/hostname structure
            if last.endswith('#') or last.endswith('$') or (len(last) < 2 and last in ['#', '$']):
                 lines.pop()
            else:
                break
                
        return "\n".join(lines).strip()

    def send_file(self, local_path: str, remote_path: str):
        # User requirement says: "I need send files from Desktop using ssh (not using UART)."
        # So this path might be invalid for UART mode, OR we might assume
        # this means specific APS file transfer which is NOT supported via UART here.
        raise NotImplementedError("File transfer over UART is not supported. Use SSH mode.")

    def get_file(self, remote_path: str, local_path: str):
        raise NotImplementedError("File retrieval via UART is not supported.")
