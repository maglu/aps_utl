import sys
import os
import re

from src.ssh_comm import SSHCommunicator
from src.bbb_uart_comm import BBBConnection

def get_communicator(target_name, target_conf, debug=False):
    mode = target_conf.get('mode')
    if mode == 'ssh':
        return SSHCommunicator(
            host=target_conf['ip'],
            port=int(target_conf.get('port', 22)),
            username=target_conf.get('username'),
            password=target_conf.get('password'),
            verbose=debug
        )
    elif mode == 'uart':
        return BBBConnection(
            host=target_conf['ip'],
            username=target_conf.get('username'),
            password=target_conf.get('password'),
            uart_port=target_conf.get('uart_port'),
            baudrate=int(target_conf.get('baudrate', 115200)),
            uart_login=target_conf.get('uart_login'),
            uart_password=target_conf.get('uart_password'),
            verbose=debug
        )
    else:
        raise ValueError(f"Unknown mode '{mode}' for target '{target_name}'. Supported: ssh, uart")

def run_action(comm, args, target_name, mode, debug=False):
    """
    Executes an action (interactive shell, command, send file, get file) on a connected communicator.
    Does not handle macros because aps_env and aps_ctl handle macros very differently.
    """
    if getattr(args, 'interactive', False):
        try:
            comm.start_interactive_shell()
        except KeyboardInterrupt:
            print("\nInteractive session ended.")
        except Exception as e:
            print(f"Error during interactive session: {e}")
        return

    command_to_run = getattr(args, 'command', None)
    
    if command_to_run:
        if debug:
            print(f"Executing on {target_name}: {command_to_run}")
        response = comm.send_command(command_to_run)
        print(f"# {command_to_run}\n{response}")
        return
        
    send_args = getattr(args, 'send', None)
    if send_args:
        if len(send_args) > 2:
            print("Error: --send accepts at most 2 arguments (LOCAL [REMOTE]).")
            sys.exit(1)
        
        local_path = send_args[0]
        if len(send_args) == 2:
            remote_path = send_args[1]
        else:
            remote_path = os.path.basename(local_path)
            
        try:
            comm.send_file(local_path, remote_path)
        except NotImplementedError:
            print(f"Error: File transfer is not supported for target '{target_name}' (mode: {mode}).")
        return
            
    get_args = getattr(args, 'get', None)
    if get_args:
        if len(get_args) > 2:
            print("Error: --get accepts at most 2 arguments (REMOTE [LOCAL]).")
            sys.exit(1)

        remote_path = get_args[0]
        if len(get_args) == 2:
            local_path = get_args[1]
        else:
            local_path = os.path.basename(remote_path)
            
        try:
            comm.get_file(remote_path, local_path)
        except NotImplementedError:
            print(f"Error: File retrieval is not supported for target '{target_name}' (mode: {mode}).")
        return
        
    print("Error: No command, macro, or file transfer specified.")
    sys.exit(1)
