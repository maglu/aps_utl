#!/usr/bin/env python3
import argparse
import sys
import os
import json
import re
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*Blowfish has been deprecated.*")
    import paramiko

from src.executor import get_communicator, run_action

def get_session_id():
    tmux_pane = os.environ.get('TMUX_PANE')
    if tmux_pane:
        return tmux_pane.replace('%', 'pane_')
    return str(os.getppid())

def get_state_file():
    return f"/tmp/.aps_target_state_{get_session_id()}"

def load_state():
    state_file = get_state_file()
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return f.read().strip()
    return None

def save_state(device):
    with open(get_state_file(), 'w') as f:
        f.write(device)

def parse_env_file(path="network.env"):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[len('export '):]
            if '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def get_target_conf(env_vars, device, entity):
    prefix = f"APS_{device.upper()}_{entity.upper()}_"
    conf = {}
    for k, v in env_vars.items():
        if k.startswith(prefix):
            key = k[len(prefix):].lower()
            conf[key] = v
            
    if 'ip' not in conf:
        return None
    return conf

def load_macros(path="aps_macros.json"):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)

def substitute_env_vars(cmd, env_vars):
    def repl(match):
        var_name = match.group(1) or match.group(2)
        val = os.environ.get(var_name)
        if val is None:
            val = env_vars.get(var_name)
        if val is None:
            raise ValueError(f"Required environment variable '{var_name}' is not set.")
        return val
    return re.sub(r'\$\{([^}]+)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)', repl, cmd)

def get_macro_info(macro_def):
    if isinstance(macro_def, dict):
        steps = macro_def.get('steps', [])
        desc = macro_def.get('description', '')
        is_internal = macro_def.get('internal', False)
    else:
        steps = macro_def
        desc = ''
        is_internal = False
    
    max_arg = -1
    env_vars_req = set()
    for step in steps:
        target = step.get('target', '')
        cmd = step.get('command', '')
        
        # Find all {N} and $VAR
        for s in (target, cmd):
            if not s: continue
            matches = re.findall(r'\{(\d+)\}', s)
            for m in matches:
                max_arg = max(max_arg, int(m))
            env_matches = re.findall(r'\$\{([^}]+)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)', s)
            for m in env_matches:
                var_name = m[0] or m[1]
                env_vars_req.add(var_name)
                
    req_args = max_arg + 1
    return steps, desc, req_args, is_internal, sorted(list(env_vars_req))

def main():
    macros = load_macros()
    mm_defs = macros.get('macros', {})

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage:")
        print("  aps_env load <device>")
        print("  aps_env --info")
        print("  aps_env <entity> [command]")
        print("\nAvailable Macros:")
        for m_name, m_def in mm_defs.items():
            _, desc, req_args, is_internal, env_vars_req = get_macro_info(m_def)
            if is_internal:
                continue
            args_str = " ".join([f"<arg{i}>" for i in range(req_args)])
            m_disp = f"{m_name} {args_str}".strip()
            env_str = f" [req env: {', '.join(env_vars_req)}]" if env_vars_req else ""
            print(f"  {m_disp:<35} {desc}{env_str}")
        sys.exit(0 if len(sys.argv) > 1 else 1)

    cmd_first = sys.argv[1]

    # Handle `load <device>`
    if cmd_first == "load":
        if len(sys.argv) < 3:
            print("Error: specify device to load (e.g., aps_env load dev1)")
            sys.exit(1)
        device = sys.argv[2]
        env_vars = parse_env_file()
        
        # Validate device exists in network.env
        rt_conf = get_target_conf(env_vars, device, 'rt')
        nrt_conf = get_target_conf(env_vars, device, 'nrt')
        if not rt_conf and not nrt_conf:
            print(f"Error: Device cluster '{device}' not found in network.env")
            sys.exit(1)
            
        save_state(device)
        print(f"Device '{device}' loaded into active session.")
        return

    # Handle `--info`
    if cmd_first in ("--info", "-i"):
        device = load_state()
        if not device:
            print("No active device. Use 'aps_env load <device>' first.")
            sys.exit(1)
            
        env_vars = parse_env_file()
        print(f"Active Device Cluster: {device}")
        for entity in ['rt', 'nrt', 'bbb']:
            conf = get_target_conf(env_vars, device, entity)
            if conf:
                port_str = f":{conf['port']}" if 'port' in conf else ""
                print(f"  - {entity.upper()}: {conf.get('mode')} @ {conf.get('ip')}{port_str}")
                
        print("\nEnvironment Variables:")
        if not env_vars:
            print("  (None found)")
        else:
            for k, v in env_vars.items():
                print(f"  {k}={v}")
        return

    # Must have a loaded device for any execution
    device = load_state()
    if not device:
        print("Error: No active device. Use 'aps_env load <device>' first.")
        sys.exit(1)
        
    env_vars = parse_env_file()

    macros = load_macros()
    mm_defs = macros.get('macros', {})

    is_mm = False
    macro_name = None
    macro_args = []

    # Handle multi-macro execution
    if cmd_first in ("-mm", "--mmacro"):
        if len(sys.argv) < 3:
            print("Error: specify multi-macro name")
            sys.exit(1)
        macro_name = sys.argv[2]
        macro_args = sys.argv[3:]
        is_mm = True
    elif cmd_first in mm_defs:
        macro_name = cmd_first
        macro_args = sys.argv[2:]
        is_mm = True

    if is_mm:
        if macro_name not in mm_defs:
            print(f"Error: Macro '{macro_name}' not found in aps_macros.json")
            sys.exit(1)
            
        macro_def = mm_defs[macro_name]
        steps, desc, req_args, _, env_vars_req = get_macro_info(macro_def)
        
        if len(macro_args) < req_args:
            args_str = " ".join([f"<arg{i}>" for i in range(req_args)])
            env_str = f" [req env: {', '.join(env_vars_req)}]" if env_vars_req else ""
            print(f"Error: Incomplete options for macro '{macro_name}'")
            print(f"Usage: aps_env {macro_name} {args_str}{env_str}".strip())
            missing = req_args - len(macro_args)
            missing_args = " ".join([f"<arg{i}>" for i in range(len(macro_args), req_args)])
            print(f"You missed {missing} argument(s): {missing_args}")
            sys.exit(1)
            
        missing_envs = [var for var in env_vars_req if os.environ.get(var) is None and env_vars.get(var) is None]
        if missing_envs:
            print(f"Error: Missing required environment variable(s) for macro '{macro_name}': {', '.join(missing_envs)}")
            sys.exit(1)
            
        communicators = {}
        
        try:
            for i, step in enumerate(steps, 1):
                entity = step.get('target')
                cmd = step.get('command')
                
                if not cmd:
                    print(f"Error: Step {i} missing 'command'.")
                    continue

                if not entity:
                    # Execute locally
                    for idx, arg_val in enumerate(macro_args):
                        cmd = cmd.replace(f"{{{idx}}}", str(arg_val))
                    if re.search(r'\{\d+\}', cmd):
                        print(f"Error: Not enough arguments provided for multi-macro command '{step.get('command')}'.")
                        sys.exit(1)
                    try:
                        cmd_resolved = substitute_env_vars(cmd, env_vars)
                    except ValueError as e:
                        print(f"Error substituting variables in step {i}: {e}")
                        sys.exit(1)
                    print(f"[LOCAL] # {cmd_resolved}")
                    os.system(cmd_resolved)
                    continue

                # Substitute positional arguments
                for idx, arg_val in enumerate(macro_args):
                    entity = entity.replace(f"{{{idx}}}", str(arg_val))
                    cmd = cmd.replace(f"{{{idx}}}", str(arg_val))
                    
                if re.search(r'\{\d+\}', entity):
                    print(f"Error: Not enough arguments provided for multi-macro target '{step.get('target')}'.")
                    sys.exit(1)
                if re.search(r'\{\d+\}', cmd):
                    print(f"Error: Not enough arguments provided for multi-macro command '{step.get('command')}'.")
                    sys.exit(1)
                    
                target_conf = get_target_conf(env_vars, device, entity)
                if not target_conf:
                    print(f"Error: Entity '{entity}' configuration not found for '{device}' in network.env.")
                    continue
                    
                # Substitute variables
                try:
                    cmd_resolved = substitute_env_vars(cmd, env_vars)
                except ValueError as e:
                    print(f"Error substituting variables in step {i}: {e}")
                    sys.exit(1)
                    
                print(f"[{device.upper()} {entity.upper()}] # {cmd_resolved}")
                
                if entity not in communicators:
                    comm = get_communicator(f"{device}_{entity}", target_conf)
                    comm.connect()
                    communicators[entity] = comm
                    
                resp = communicators[entity].send_command(cmd_resolved)
                print(resp)
        finally:
            for c in communicators.values():
                try: c.disconnect()
                except: pass
        return

    # Handle `<entity> [command|args]`
    entity = cmd_first
    target_conf = get_target_conf(env_vars, device, entity)
    if not target_conf:
        print(f"Error: Entity '{entity}' configuration not found for '{device}' in network.env.")
        sys.exit(1)

    # Use argparse for the rest of the arguments to re-use run_action logic easily
    parser = argparse.ArgumentParser(prog=f"aps_env {entity}")
    parser.add_argument('command', nargs='?', help="Command to execute")
    parser.add_argument('-d', '--debug', action='store_true', help="Enable debug output")
    parser.add_argument('-i', '--interactive', action='store_true', help="Start an interactive shell session")
    parser.add_argument('-s', '--send', nargs='+', metavar=('LOCAL', 'REMOTE'), help="Send file")
    parser.add_argument('-g', '--get', nargs='+', metavar=('REMOTE', 'LOCAL'), help="Get file")
    
    args = parser.parse_args(sys.argv[2:])
    
    comm = get_communicator(f"{device}_{entity}", target_conf, getattr(args, 'debug', False))
    try:
        comm.connect()
        run_action(comm, args, f"{device.upper()} {entity.upper()}", target_conf.get('mode', ''), getattr(args, 'debug', False))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        try: comm.disconnect()
        except: pass

if __name__ == "__main__":
    main()
