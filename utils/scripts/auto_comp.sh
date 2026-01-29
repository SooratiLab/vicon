#!/usr/bin/env bash

# ============================================================================
# Vicon Commands Auto-Completion for Bash
# 
# COMMANDS:
#
# vicon-env
#   Activate Python environment for vicon package
#   No arguments
#
# vicon-stream
#   Start Vicon data streamer - streams tracking data from Vicon system
#   --host <ip>      : Vicon Tracker host address (default: localhost)
#   --port <num>     : Vicon Tracker port number (default: 801)
#   --rate <hz>      : Streaming rate in Hz (default: 100)
#   --pose           : Stream only position and orientation data
#   --all            : Stream all geometry data (segments + markers)
#   --frames         : Include camera frame metadata
#   --verbose        : Enable verbose logging
#   -h, --help       : Show help message
#
# vicon-listen
#   Start Vicon data listener - receives and processes streamed data
#   --host <ip>      : Server host to listen on (default: localhost)
#   --port <num>     : Server port to listen on (default: 5555)
#   --save           : Save received data to CSV files
#   --output <dir>   : Output directory for CSV files
#   --verbose        : Enable verbose logging
#   -h, --help       : Show help message
#
# USAGE:
#   Source this file in your ~/.bashrc or manually:
#     source /path/to/auto_comp.sh
#============================================================================


# Determine repository path from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_PATH="$(dirname "$(dirname "$SCRIPT_DIR")")"
REPO_NAME="$(basename "$REPO_PATH")"
ENV_NAME="$REPO_NAME"
ENV_PATH="$HOME/envs/$ENV_NAME"

# Command Definitions

# vicon-env: Activate Python environment
vicon-env() {
    local activate_script="$ENV_PATH/bin/activate"
    if [[ -f "$activate_script" ]]; then
        source "$activate_script"
    else
        echo "[ERROR] Virtual environment not found at: $ENV_PATH" >&2
        return 1
    fi
}

# vicon-stream: Start Vicon data streamer
vicon-stream() {
    local python_exe="$ENV_PATH/bin/python"
    local script="$REPO_PATH/src/data_streamer.py"
    
    if [[ ! -f "$python_exe" ]]; then
        echo "[ERROR] Python not found at: $python_exe" >&2
        return 1
    fi
    
    if [[ ! -f "$script" ]]; then
        echo "[ERROR] Script not found at: $script" >&2
        return 1
    fi
    
    "$python_exe" "$script" "$@"
}

# vicon-listen: Start Vicon data listener
vicon-listen() {
    local python_exe="$ENV_PATH/bin/python"
    local script="$REPO_PATH/src/data_listener.py"
    
    # Use venv python if available, otherwise fall back to system python
    if [[ ! -f "$python_exe" ]]; then
        python_exe="python3"
    fi
    
    if [[ ! -f "$script" ]]; then
        echo "[ERROR] Script not found at: $script" >&2
        return 1
    fi
    
    "$python_exe" "$script" "$@"
}

# Auto-Completion Functions

_vicon_env() {
    return 0
}

_vicon_stream() {
    local cur prev words cword
    
    if declare -F _init_completion >/dev/null 2>&1; then
        _init_completion || return
    else
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
    fi
    
    local opts=(
        "--host"
        "--port"
        "--rate"
        "--pose"
        "--all"
        "--frames"
        "--verbose"
        "--help"
        "-h"
    )
    
    case "$prev" in
        --host)
            COMPREPLY=( $(compgen -W "localhost 127.0.0.1" -- "$cur") )
            return 0
            ;;
        --port)
            COMPREPLY=( $(compgen -W "801" -- "$cur") )
            return 0
            ;;
        --rate)
            COMPREPLY=( $(compgen -W "30 60 100 120" -- "$cur") )
            return 0
            ;;
        --help|-h)
            return 0
            ;;
    esac
    
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts[*]}" -- "$cur") )
        return 0
    fi
    
    return 0
}

_vicon_listen() {
    local cur prev words cword
    
    if declare -F _init_completion >/dev/null 2>&1; then
        _init_completion || return
    else
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
    fi
    
    local opts=(
        "--host"
        "--port"
        "--save"
        "--output"
        "--verbose"
        "--help"
        "-h"
    )
    
    case "$prev" in
        --host)
            COMPREPLY=( $(compgen -W "localhost 127.0.0.1" -- "$cur") )
            return 0
            ;;
        --port)
            COMPREPLY=( $(compgen -W "5555" -- "$cur") )
            return 0
            ;;
        --output)
            COMPREPLY=( $(compgen -d -- "$cur") )
            return 0
            ;;
        --help|-h)
            return 0
            ;;
    esac
    
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts[*]}" -- "$cur") )
        return 0
    fi
    
    return 0
}

# Register Completion Functions
complete -F _vicon_env vicon-env
complete -F _vicon_stream vicon-stream
complete -F _vicon_listen vicon-listen

# Export Functions for subshells
export -f vicon-env
export -f vicon-stream
export -f vicon-listen

# Aliases for convenience
alias vl='vicon-listen --host 100.89.223.68'
alias vlplot='vicon-listen --host 100.89.223.68 --plot'

