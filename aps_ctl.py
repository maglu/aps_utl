#!/usr/bin/env python3
import argparse
import argparse
import sys
import warnings
import os
import subprocess

# Suppress CryptographyDeprecationWarning from paramiko
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*Blowfish has been deprecated.*")
    import paramiko

from src.config_loader import load_config
from src.ssh_comm import SSHCommunicator
from src.bbb_uart_comm import BBBConnection

def _get_communicator(target_name, target_conf, debug=False):
    mode = target_conf.get('mode')
    if mode == 'ssh':
        return SSHCommunicator(
            host=target_conf['ip'],
            port=target_conf['port'],
            username=target_conf['username'],
            password=target_conf['password'],
            verbose=debug
        )
    elif mode == 'uart':
        return BBBConnection(
            host=target_conf['ip'],
            username=target_conf['username'],
            password=target_conf['password'],
            uart_port=target_conf['uart_port'],
            baudrate=target_conf['baudrate'],
            uart_login=target_conf.get('uart_login'),
            uart_password=target_conf.get('uart_password'),
            verbose=debug
        )
    else:
        raise ValueError(f"Unknown mode '{mode}' for target '{target_name}'. Supported: ssh, uart")

def main():
    parser = argparse.ArgumentParser(description="APS Control CLI")
    
    # New Usage: ./aps_ctl.py [target] [command] etc.
    parser.add_argument('target', nargs='?', help="Target device name (e.g. aps, bbb) defined in aps_config.json")
    parser.add_argument('command', nargs='?', help="Command to execute (optional if --macro, --mmacro, or file transfer used)")
    
    parser.add_argument('-d', '--debug', action='store_true', help="Enable debug output")
    parser.add_argument('-i', '--interactive', action='store_true', help="Start an interactive shell session")
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-m', '--macro', help="Name of macro to execute")
    group.add_argument('-mm', '--mmacro', help="Name of multi-macro to execute")
    parser.add_argument('-s', '--send', nargs='+', metavar=('LOCAL', 'REMOTE'), help="Send file (local [remote])")
    parser.add_argument('-g', '--get', nargs='+', metavar=('REMOTE', 'LOCAL'), help="Get file (remote [local])")
    group.add_argument('-l', '--list-macros', action='store_true', help="List available macros")

    args = parser.parse_args()
    
    # Load Config
    config = load_config("aps_config.json")
    
    # Handle list-macros early
    if args.list_macros:
        print("Available Macros:")
        for name, cmds in config.get('macros', {}).items():
            print(f"  - {name}: {len(cmds)} commands")
        print("\nAvailable Multi-Macros:")
        for name, cmds in config.get('multi_macros', {}).items():
            print(f"  - {name}: {len(cmds)} steps")
        return

    # Validate Target is present (required for all other operations except multi-macro)
    if not args.target and not args.mmacro:
        parser.print_usage()
        print("Error: standard usage requires a target argument or --mmacro.")
        sys.exit(1)

    # Validate Target exists in config (if provided)
    if args.target and args.target not in config:
        print(f"Error: Target '{args.target}' not found in configuration.")
        available_targets = [k for k in config.keys() if k not in ('macros', 'multi_macros')]
        print(f"Available targets: {available_targets}")
        sys.exit(1)
        
    communicators = {}
    
    try:
        if args.mmacro:
            multi_macro_cmds = config.get('multi_macros', {}).get(args.mmacro)
            if not multi_macro_cmds:
                print(f"Error: Multi-Macro '{args.mmacro}' not found in configuration.")
                sys.exit(1)
            
            if args.debug:
                print(f"Executing Multi-Macro: {args.mmacro} ({len(multi_macro_cmds)} steps)")
            
            for i, step in enumerate(multi_macro_cmds, 1):
                target = step.get('target')
                cmd = step.get('command')
                
                if not cmd:
                    print(f"Error: Step {i} is missing 'command' field.")
                    continue
                    
                if target is None:
                    target_str = "local"
                else:
                    target_str = target

                if args.debug:
                    print(f"[{i}/{len(multi_macro_cmds)}] Target: {target_str} | Cmd: {cmd}")
                else:
                    print(f"[{target_str}] # {cmd}")
                    
                if target is None:
                    try:
                        result = subprocess.run(cmd, shell=True, check=True, text=True, capture_output=True)
                        if result.stdout:
                            print(result.stdout, end="")
                        if result.stderr:
                            sys.stderr.write(result.stderr)
                    except subprocess.CalledProcessError as e:
                        msg = f"Local command failed with exit code {e.returncode}\n"
                        if e.stdout:
                            msg += e.stdout
                        if e.stderr:
                            msg += e.stderr
                        raise RuntimeError(msg.strip())
                else:
                    if target not in config:
                        print(f"Error: Target '{target}' in multi-macro not found in config.")
                        continue
                        
                    if target not in communicators:
                        try:
                            t_conf = config[target]
                            if 'mode' not in t_conf:
                                print(f"Error: Target '{target}' is missing 'mode'.")
                                continue
                            comm = _get_communicator(target, t_conf, args.debug)
                            comm.connect()
                            communicators[target] = comm
                        except Exception as e:
                            print(f"Error connecting to target '{target}': {e}")
                            continue
                            
                    comm = communicators[target]
                    resp = comm.send_command(cmd)
                    print(resp)
        else:
            target_conf = config[args.target]
            mode = target_conf.get('mode')
            
            if not mode:
                print(f"Error: Target '{args.target}' configuration is missing 'mode' field.")
                sys.exit(1)

            # Initialize Communicator
            comm = _get_communicator(args.target, target_conf, args.debug)
            comm.connect()
            communicators[args.target] = comm
            
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
                print(f"# {command_to_run}\n{response}")
                
            elif args.macro:
                macro_cmds = config.get('macros', {}).get(args.macro)
                if not macro_cmds:
                    print(f"Error: Macro '{args.macro}' not found in configuration.")
                    sys.exit(1)
                
                if args.debug:
                    print(f"Executing Macro: {args.macro} ({len(macro_cmds)} steps) on {args.target}")
                for i, cmd in enumerate(macro_cmds, 1):
                    if args.debug:
                        print(f"[{i}/{len(macro_cmds)}] {cmd}")
                    else:
                        print(f"[{args.target}] # {cmd}")
                    resp = comm.send_command(cmd)
                    print(resp)
                    
            elif args.send:
                if len(args.send) > 2:
                    print("Error: --send accepts at most 2 arguments (LOCAL [REMOTE]).")
                    sys.exit(1)
                
                local_path = args.send[0]
                if len(args.send) == 2:
                    remote_path = args.send[1]
                else:
                    remote_path = os.path.basename(local_path)
                    
                try:
                    comm.send_file(local_path, remote_path)
                except NotImplementedError:
                    print(f"Error: File transfer is not supported for target '{args.target}' (mode: {mode}).")
                    
            elif args.get:
                if len(args.get) > 2:
                    print("Error: --get accepts at most 2 arguments (REMOTE [LOCAL]).")
                    sys.exit(1)

                remote_path = args.get[0]
                if len(args.get) == 2:
                    local_path = args.get[1]
                else:
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
        # Ensure we exit with failure status if any exception (e.g., command failure) occurred.
        # We need to cleanup connections first, but Python doesn't allow 'finally' to stop exit without complicated logic.
        # We will set a flag or just let 'finally' run and assume sys.exit(1) inside except skips finally?
        # Actually sys.exit raises SystemExit which 'finally' handles before actually exiting!
        sys.exit(1)
    finally:
        for c in communicators.values():
            try:
                c.disconnect()
            except:
                pass

if __name__ == "__main__":
    main()
