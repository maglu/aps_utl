#!/usr/bin/env python3
import argparse
import argparse
import sys
import warnings
import os

# Suppress CryptographyDeprecationWarning from paramiko
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*Blowfish has been deprecated.*")
    import paramiko

from src.config_loader import load_config
from src.ssh_comm import SSHCommunicator
from src.bbb_uart_comm import BBBConnection

def main():
    parser = argparse.ArgumentParser(description="APS Control CLI")
    
    # New Usage: ./aps_ctl.py [target] [command] etc.
    parser.add_argument('target', help="Target device name (e.g. aps, bbb) defined in config.json")
    parser.add_argument('command', nargs='?', help="Command to execute (optional if --macro or --send-file used)")
    
    parser.add_argument('-d', '--debug', action='store_true', help="Enable debug output")
    parser.add_argument('-i', '--interactive', action='store_true', help="Start an interactive shell session")
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--macro', help="Name of macro to execute")
    parser.add_argument('--send-file', metavar='LOCAL', help="Send file (uses basename for remote)")
    parser.add_argument('--get-file', metavar='REMOTE', help="Get file (saves to basename in current dir)")
    group.add_argument('--list-macros', action='store_true', help="List available macros")

    args = parser.parse_args()
    
    # Load Config
    config = load_config("config.json")
    
    # Handle list-macros early? (Maybe doesn't need target? But usage says ./aps_ctl.py [target] ... so target is mandatory)
    if args.list_macros:
        print("Available Macros:")
        for name, cmds in config.get('macros', {}).items():
            print(f"  - {name}: {len(cmds)} commands")
        return

    # Validate Target
    if args.target not in config:
        # Check if 'macros' is accidentally passed as target (edge case), but config structure distinguishes
        print(f"Error: Target '{args.target}' not found in configuration.")
        print(f"Available targets: {[k for k in config.keys() if k != 'macros']}")
        sys.exit(1)
        
    target_conf = config[args.target]
    mode = target_conf.get('mode')
    
    if not mode:
        print(f"Error: Target '{args.target}' configuration is missing 'mode' field.")
        sys.exit(1)

    # Initialize Communicator
    comm = None
    try:
        if mode == 'ssh':
            comm = SSHCommunicator(
                host=target_conf['ip'],
                port=target_conf['port'],
                username=target_conf['username'],
                password=target_conf['password'],
                verbose=args.debug
            )
        elif mode == 'uart':
            comm = BBBConnection(
                host=target_conf['ip'],
                username=target_conf['username'],
                password=target_conf['password'],
                uart_port=target_conf['uart_port'],
                baudrate=target_conf['baudrate'],
                uart_login=target_conf.get('uart_login'),
                uart_password=target_conf.get('uart_password'),
                verbose=args.debug
            )
        else:
            print(f"Error: Unknown mode '{mode}' for target '{args.target}'. Supported: ssh, uart")
            sys.exit(1)
            
        comm.connect()
        
        # Handle Interactive Mode
        if args.interactive:
            try:
                comm.start_interactive_shell()
            except KeyboardInterrupt:
                print("\nInteractive session ended.")
            except Exception as e:
                print(f"Error during interactive session: {e}")
            finally:
                comm.disconnect()
                sys.exit(0)

        # Determine action
        command_to_run = args.command
        
        if command_to_run:
            if args.debug:
                print(f"Executing on {args.target}: {command_to_run}")
            response = comm.send_command(command_to_run)
            print(f"Response:\n{response}")
            
        elif args.macro:
            macro_cmds = config.get('macros', {}).get(args.macro)
            if not macro_cmds:
                print(f"Error: Macro '{args.macro}' not found in configuration.")
                comm.disconnect()
                sys.exit(1)
            
            if args.debug:
                print(f"Executing Macro: {args.macro} ({len(macro_cmds)} steps) on {args.target}")
            for i, cmd in enumerate(macro_cmds, 1):
                if args.debug:
                    print(f"[{i}/{len(macro_cmds)}] {cmd}")
                resp = comm.send_command(cmd)
                print(f"Output: {resp}")
                
        elif args.send_file:
            local_path = args.send_file
            remote_path = os.path.basename(local_path)
            try:
                comm.send_file(local_path, remote_path)
            except NotImplementedError:
                print(f"Error: File transfer is not supported for target '{args.target}' (mode: {mode}).")
                
        elif args.get_file:
            remote_path = args.get_file
            local_path = os.path.basename(remote_path)
            try:
                comm.get_file(remote_path, local_path)
            except NotImplementedError:
                print(f"Error: File retrieval is not supported for target '{args.target}' (mode: {mode}).")
        else:
            # No action specified
             print("Error: No command, macro, or file transfer specified.")
             sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if comm:
            comm.disconnect()

if __name__ == "__main__":
    main()
