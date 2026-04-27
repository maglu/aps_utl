#!/bin/bash
# Helper script to launch tmux with panes connected to different devices/entities

if [ -z "$1" ]; then
    echo "Usage: ./aps_tmux.sh <device>"
    echo "Example: ./aps_tmux.sh dev1"
    exit 1
fi

DEVICE=$1
SESSION="aps-$DEVICE"

tmux has-session -t $SESSION 2>/dev/null

if [ $? != 0 ]; then
    # Create new session, name the first window
    tmux new-session -d -s $SESSION -n "RT"
    
    # Load the device in the first pane
    tmux send-keys -t $SESSION:0 "./.venv/bin/python aps.py load $DEVICE" C-m
    
    # Window 1 (nrt)
    tmux new-window -t $SESSION:1 -n 'nrt'
    tmux send-keys -t $SESSION:1 "./.venv/bin/python aps.py load $DEVICE" C-m
    
    # Window 2 (bbb)
    tmux new-window -t $SESSION:2 -n 'bbb'
    tmux send-keys -t $SESSION:2 "./.venv/bin/python aps.py load $DEVICE" C-m
    
    # Select first window
    tmux select-window -t $SESSION:0
fi

# Attach to the session
tmux attach-session -t $SESSION
