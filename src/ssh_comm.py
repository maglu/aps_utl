import paramiko
import os
import stat
import sys
import socket
from .communicator import Communicator

class SSHCommunicator(Communicator):
    def __init__(self, host, port, username, password, verbose=False):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.verbose = verbose
        self.client = None
        self.sftp = None

    def log(self, msg):
        if self.verbose:
            print(msg)

    def _print_progress(self, transferred, total):
        # Simple progress bar logic
        percentage = (transferred / total) * 100
        # Print carriage return to overwrite line, flush stdout
        sys.stdout.write(f"\rTransferring: {percentage:.1f}% ({transferred}/{total} bytes)")
        sys.stdout.flush()
        if transferred >= total:
            sys.stdout.write("\n")

    def connect(self):
        try:
            self.client = paramiko.SSHClient()
            # StrictHostKeyChecking=no equivalent
            # We do NOT load system host keys.
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.log(f"Connecting to {self.host}:{self.port} via SSH...")
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10,
                banner_timeout=30
            )
            self.log("SSH Connection established.")

        except paramiko.AuthenticationException:
            self.log("Authentication failed. Trying 'none' authentication method...")
            try:
                # Fallback: Try "none" authentication manually
                t = paramiko.Transport((self.host, self.port))
                t.start_client(timeout=10)
                # To emulate AutoAddPolicy (skip verification primarily), we just proceed?
                # Transport doesn't verify until we ask it to?
                # Actually, verify_key is called by start_client if we provide logic.
                # By default it doesn't fail on unknown keys if we don't set a strict mechanism?
                # Actually we can just create a new client logic.
                
                try:
                    t.auth_none(self.username)
                    # Success
                    self.client = paramiko.SSHClient()
                    self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    self.client._transport = t
                    self.log("Connected via 'none' authentication.")
                except Exception as e:
                     t.close()
                     raise e
            except Exception as e:
                raise ConnectionError(f"Failed to connect via SSH (including 'none'): {e}")

        except paramiko.SSHException as e:
            # Handle "No existing session" which can happen if keys fail and we need to try password/none
            if "No existing session" in str(e):
                self.log(f"Initial connection failed ({e}), retrying with explicit options...")
                try:
                    self.client.connect(
                        hostname=self.host,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        timeout=10,
                        banner_timeout=30,
                        look_for_keys=False,
                        allow_agent=False
                    )
                    self.log("SSH Connection established (retry).")
                    return
                except Exception as retry_e:
                    self.log(f"Retry failed: {retry_e}")
                    # Fall through to other handlers or raise
                    if not isinstance(retry_e, paramiko.AuthenticationException):
                        raise retry_e

            # If it wasn't "No existing session" or retry failed with non-Auth error, re-raise
            if "No existing session" not in str(e):
                raise e

        except Exception as e:
            raise ConnectionError(f"Failed to connect via SSH: {e}")

    def disconnect(self):
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()
            self.log("SSH Connection closed.")

    def send_command(self, cmd: str) -> str:
        if not self.client:
            raise ConnectionError("Not connected.")
        
        # print(f"Sending command: {cmd}")
        stdin, stdout, stderr = self.client.exec_command(cmd)
        
        # Read output
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        
        if err:
             # Depending on requirements, we might want to return stderr too or raise exception
             # For now, append it if present
             return f"{out}\nError: {err}".strip()
        return out

    def send_file(self, local_path: str, remote_path: str):
        if not self.client:
            raise ConnectionError("Not connected.")
        
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
            
        self.log(f"Sending file {local_path} to {remote_path}...")
        try:
            if not self.sftp:
                self.sftp = self.client.open_sftp()
            
            # Handle tilde expansion for remote path (simple case for current user)
            if remote_path.startswith('~/'):
                try:
                    # Get home directory
                    self.sftp.chdir('.')
                    home = self.sftp.getcwd()
                    remote_path = os.path.join(home, remote_path[2:])
                except:
                    # Fallback or ignore if fails
                    pass
            
            # Check if remote_path is a directory
            # Check if remote_path is a directory
            try:
                r_stat = self.sftp.stat(remote_path)
                if stat.S_ISDIR(r_stat.st_mode):
                    # It is a directory, append local filename
                    # Assume unix-style remote paths
                    if not remote_path.endswith('/'):
                        remote_path += '/'
                    remote_path += os.path.basename(local_path)
                    self.log(f"Target is a directory, sending to: {remote_path}")
            except IOError:
                # Path doesn't exist, assume it's the target filename
                pass

            self.sftp.put(local_path, remote_path, callback=self._print_progress)
            
            # Preserve attributes (SFTP)
            st = os.stat(local_path)
            self.sftp.chmod(remote_path, stat.S_IMODE(st.st_mode))
            self.sftp.utime(remote_path, (int(st.st_atime), int(st.st_mtime)))
            
            self.log("File transfer complete (SFTP).")
        except Exception as e:
            self.log(f"SFTP failed ({e}), trying SCP fallback...")
            try:
                self._send_file_scp(local_path, remote_path)
            except Exception as scp_e:
                raise RuntimeError(f"File transfer failed (SFTP: {e}, SCP: {scp_e})")

    def _send_file_scp(self, local_path, remote_path):
        """
        Simple SCP implementation using 'scp -t' on remote.
        """
        import os
        
        st = os.stat(local_path)
        file_size = st.st_size
        mode = stat.S_IMODE(st.st_mode)
        basename = os.path.basename(remote_path)
        
        # Open a channel for SCP
        # -p option tells remote scp to expect time/mode commands
        chan = self.client.get_transport().open_session()
        chan.exec_command(f"scp -t -p {remote_path}")
        
        # Protocol: Wait for 0x00
        if chan.recv(1) != b'\x00':
            raise RuntimeError("SCP: Failed to initiate transfer")

        # Send T command (Timestamps): T<mtime> 0 <atime> 0
        cmd_t = f"T{int(st.st_mtime)} 0 {int(st.st_atime)} 0\n"
        chan.sendall(cmd_t.encode())
        
        # Wait for 0x00
        if chan.recv(1) != b'\x00':
             raise RuntimeError("SCP: Remote rejected timestamps")
            
        # Send C command: C<perms> <size> <filename>\n
        cmd_c = f"C{mode:04o} {file_size} {basename}\n"
        chan.sendall(cmd_c.encode())
        
        # Wait for 0x00
        if chan.recv(1) != b'\x00':
            raise RuntimeError("SCP: Remote rejected file info")
            
        # Send content in chunks
        chunk_size = 16384 # 16KB chunks
        sent = 0
        with open(local_path, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                chan.sendall(data)
                sent += len(data)
                self._print_progress(sent, file_size)
                # self.log(f"Sent chunk ({len(data)} bytes, total: {sent}/{file_size})")

        # Send 0x00 to ends
        chan.send(b'\x00')
        
        # Wait for 0x00
        if chan.recv(1) != b'\x00':
            raise RuntimeError("SCP: Remote did not acknowledge transfer completion")
            
        chan.close()
        self.log(f"File transfer complete (SCP). Sent {sent} bytes.")

    def get_file(self, remote_path: str, local_path: str):
        if not self.client:
            raise ConnectionError("Not connected.")
            
        self.log(f"Retrieving file {remote_path} to {local_path}...")
        try:
            if not self.sftp:
                self.sftp = self.client.open_sftp()
            
            # Check if local_path is a directory
            if os.path.exists(local_path) and os.path.isdir(local_path):
                 local_path = os.path.join(local_path, os.path.basename(remote_path))
                 self.log(f"Destination is a directory, saving to: {local_path}")

            # Use callback to track progress if needed, but for now just get
            # Get attributes first (SFTP)
            attrs = self.sftp.stat(remote_path)
            
            self.sftp.get(remote_path, local_path, callback=self._print_progress)
            
            # Apply attributes locally
            if attrs:
                if attrs.st_mode:
                    os.chmod(local_path, stat.S_IMODE(attrs.st_mode))
                if attrs.st_atime and attrs.st_mtime:
                    os.utime(local_path, (attrs.st_atime, attrs.st_mtime))
                    
            self.log("File retrieval complete (SFTP).")
        except Exception as e:
            self.log(f"SFTP failed ({e}), trying SCP fallback...")
            try:
                self._get_file_scp(remote_path, local_path)
            except Exception as scp_e:
                raise RuntimeError(f"File retrieval failed (SFTP: {e}, SCP: {scp_e})")

    def start_interactive_shell(self):
        """
        Start an interactive shell session.
        Authentication is already handled by connect().
        """
        if not self.client:
            raise ConnectionError("Not connected.")

        import select
        try:
            import termios
            import tty
        except ImportError:
            raise RuntimeError("Interactive mode requires a POSIX system (termios/tty support).")

        self.log("Starting interactive SSH shell... (Press user interrupt to exit)")

        # Open a new shell channel
        chan = self.client.invoke_shell()
        
        # Save original tty settings
        old_tty = termios.tcgetattr(sys.stdin)
        
        try:
            # Set stdin to raw mode
            tty.setraw(sys.stdin.fileno())
            chan.settimeout(0.0)

            while True:
                r, w, e = select.select([chan, sys.stdin], [], [])
                
                if chan in r:
                    try:
                        x = chan.recv(1024)
                        if len(x) == 0:
                            break
                        sys.stdout.buffer.write(x)
                        sys.stdout.buffer.flush()
                    except socket.timeout:
                        pass
                
                if sys.stdin in r:
                    x = sys.stdin.read(1)
                    if len(x) == 0:
                        break
                    chan.send(x)
                    
        finally:
            # Restore tty settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)
            chan.close()
            print("\nConnection closed.")

    def _get_file_scp(self, remote_path, local_path):
        """
        Simple SCP retrieval using 'scp -f' on remote.
        """
        import re
        
        # Open a channel for SCP
        # -f option tells remote scp to send file
        # -p (preserve) is optional
        chan = self.client.get_transport().open_session()
        chan.exec_command(f"scp -f -p {remote_path}")
        
        # Protocol: Send 0x00 to start
        chan.send(b'\x00')
        
        mtime = None
        atime = None
        mode = None
        
        # Loop to handle C/D/T commands, though we expect C for a file.
        while True:
            # Read command byte
            cmd_byte = chan.recv(1)
            if not cmd_byte:
                raise RuntimeError("SCP Download: Unexpected EOF")
            
            cmd = cmd_byte.decode()
            
            if cmd == 'C': 
                # File info: C<perms> <size> <filename>
                # C0644 1234 foo.txt
                # Read until newline
                msg = b''
                while True:
                    b = chan.recv(1)
                    if b == b'\n':
                        break
                    msg += b
                
                parts = msg.decode().strip().split(' ')
                mode = int(parts[0], 8) # Octal permissions
                file_size = int(parts[1])
                # filename = " ".join(parts[2:])
                
                # Acknowledge file info
                chan.send(b'\x00')
                
                # Read content
                received = 0
                chunk_size = 16384
                with open(local_path, 'wb') as f:
                    while received < file_size:
                        # Determine how much to read
                        remaining = file_size - received
                        to_read = min(remaining, chunk_size)
                        
                        data = chan.recv(to_read)
                        if not data:
                            raise RuntimeError("SCP Download: Unexpected EOF during data")
                        
                        f.write(data)
                        received += len(data)
                        self._print_progress(received, file_size)
                
                # Verify we received it all
                # Check for the trailing 0x00 from remote?
                # Actually, remote waits for our ack after data?
                # No, protocol usually is: sending data... then wait for ack.
                # Actually scp sends data then sends 0x00? 
                # Let's check receive buffer for 0x00
                ack = chan.recv(1)
                if ack != b'\x00':
                     self.log(f"Warning: SCP Download expected 0x00 after data, got {ack}")
                
                # Send final ack
                chan.send(b'\x00')
                
                # Apply attributes if we got them
                if mode is not None:
                     os.chmod(local_path, stat.S_IMODE(mode))
                if mtime is not None and atime is not None:
                     os.utime(local_path, (atime, mtime))
                
                self.log(f"File retrieval complete (SCP). Received {received} bytes.")
                break
                # If we loop here, we might get EOF
                
            elif cmd == 'T':
                 # Timestamp info (if -p was implied or sent)
                 # T<mtime> 0 <atime> 0
                 # Just consume line and ack
                msg = b''
                while True:
                    b = chan.recv(1)
                    if b == b'\n':
                        break
                    msg += b
                
                # Parse T<mtime> 0 <atime> 0
                # e.g. T1675662366 0 1675662366 0
                parts = msg.decode().strip().split(' ')
                # Expecting 4 parts
                if len(parts) >= 4:
                     mtime = int(parts[0])
                     atime = int(parts[2])
                
                chan.send(b'\x00')
            elif cmd == 'E':
                 # End of directory (not expected for single file)
                 chan.send(b'\x00')
                 break
            elif cmd == '\x01' or cmd == '\x02':
                # Warning/Error
                msg = b''
                while True:
                    b = chan.recv(1)
                    if b == b'\n': break
                    msg += b
                raise RuntimeError(f"SCP Error: {msg.decode()}")
            else:
                # Unknown
                 pass
        
        chan.close()
