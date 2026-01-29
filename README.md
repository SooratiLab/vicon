# Vicon DataStream Broadcaster

Streaming position, orientation, and tracking data from the Robot Lab Vicon Camera Capture System over TCP for real-time robot localization and tracking.

## Features

- **Multiple Stream Modes**:
  - `--pose`: Position and orientation (segments only) - lightweight
  - `--all`: All geometry data (segments, markers, quality) - comprehensive
  - `--frames`: Camera metadata and centroids (optional)

- **High Performance**: Configurable streaming rates up to 100+ Hz
- **Low Latency**: Direct TCP streaming with minimal overhead
- **Multi-Client Support**: Multiple listeners can connect simultaneously
- **Data Logging**: Save tracking data to CSV for analysis

## Setup

### Prerequisites

Install the following software manually:
1. **Git** - Download from [git-scm.com](https://git-scm.com)
2. **Python 3.10+** - Download from [python.org](https://python.org)
3. **Vicon DataStream SDK** - Download from Vicon website (requires license)

### Automated Setup

#### Windows Setup

Run the setup script to automatically configure everything:

```powershell
# Clone the repository
git clone https://github.com/SooratiLab/vicon.git
cd vicon/utils/scripts

# Run setup script (may need to set execution policy first)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\setup.ps1
```

#### Linux Setup

For Linux systems, source the auto-completion script:

```bash
# Clone the repository
git clone https://github.com/SooratiLab/vicon.git
cd vicon/utils/scripts

# Add to your shell configuration
echo "source $(pwd)/auto_comp.sh" >> ~/.bashrc
source ~/.bashrc

# Or for zsh
echo "source $(pwd)/auto_comp.sh" >> ~/.zshrc
source ~/.zshrc
```

The setup provides:
- Python virtual environment management at `~/envs/vicon`
- Convenience commands with auto-completion
- Pre-configured aliases for common tasks

### Convenience Commands

After setup, restart your shell and use these commands from anywhere:

**Windows (PowerShell):**
```powershell
# Activate Python environment
vicon-env

# Re-run setup script
vicon-setup

# Start streaming Vicon data
vicon-stream --pose

# Listen to Vicon stream
vicon-listen --save --verbose
```

**Linux (Bash/Zsh):**
```bash
# Activate Python environment
vicon-env

# Start streaming Vicon data
vicon-stream --pose

# Listen to Vicon stream
vicon-listen --save --verbose

# Quick aliases
vl                    # Listen to remote Vicon at 100.89.223.68
vlplot                # Listen with plotting enabled
```

All commands support tab completion - press TAB after the command to see available arguments.

### Manual Setup (Alternative)

If you prefer manual setup or need to troubleshoot:

<details>
<summary>Click to expand manual setup instructions</summary>

#### 1. Create Python Environment

Using PowerShell, create a new Python environment (Python 3.10+) in **~/envs**:

Check Execution Policy:
```powershell
Get-ExecutionPolicy
```

If Execution Policy is *Restricted*, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Create and activate environment:
```powershell
mkdir -p ~/envs; cd ~/envs
python -m venv vicon
~/envs/vicon/Scripts/Activate.ps1
python -m pip install --upgrade pip
```

#### 2. Install Vicon DataStream SDK

Copy and install the Python Vicon SDK in the new environment:
```powershell
Copy-Item "$env:ProgramFiles\Vicon\DataStream SDK\Win64\Python\vicon_dssdk" "$env:USERPROFILE\vicon_dssdk" -Recurse
python -m pip install "$env:USERPROFILE\vicon_dssdk"
```

#### 3. Verify Installation

Test the installation (no errors means success):
```powershell
python -c "import vicon_dssdk"
```

</details>

## Usage

### Quick Start with Convenience Commands

After running setup and restarting PowerShell:

```powershell
# Activate environment (optional - commands work without activation)
vicon-env

# Start streaming (on Vicon system machine)
vicon-stream --pose --rate 100

# Listen to stream (on any machine)
vicon-listen --save --verbose
```

### Streaming Data (Server)

Start the Vicon data streamer on the machine connected to the Vicon system:

```bash
# Stream position and orientation at 100 Hz
python src/data_streamer.py --host localhost:801 --pose --rate 100

# Stream all geometry data
python src/data_streamer.py --host localhost:801 --all

# Stream pose with camera metadata
python src/data_streamer.py --host localhost:801 --pose --frames

# Custom broadcast port
python src/data_streamer.py --host localhost:801 --pose --port 5556
```

**Arguments:**
- `--host`: Vicon server address in `host:port` format (default: `localhost:801`)
- `--port`: TCP broadcast port for clients (default: `5555`)
- `--rate`: Target streaming rate in Hz (default: `100`)
- `--pose`: Stream position and orientation (segments)
- `--all`: Stream all geometry data (segments, markers, quality)
- `--frames`: Include camera frame metadata

### Receiving Data (Client)

Connect to the streamer from any machine on the network:

```bash
# Listen and display data
python src/data_listener.py --host localhost --port 5555

# Save data to CSV files
python src/data_listener.py --host localhost --port 5555 --save

# Verbose output with detailed position data
python src/data_listener.py --host localhost --port 5555 --verbose

# Connect to remote streamer
python src/data_listener.py --host 192.168.1.100 --port 5555 --save
```

**Arguments:**
- `--host`: Vicon streamer host address (default: `localhost`)
- `--port`: TCP port to connect to (default: `5555`)
- `--save`: Save tracking data to CSV files
- `--verbose`: Print detailed data information

### Using the Python API

For programmatic access, use the `ViconPositionListener` class:

```python
from vicon.src.position_listener import ViconPositionListener

# Create listener instance
listener = ViconPositionListener(
    host="localhost",           # Vicon streamer host
    port=5555,                   # Vicon streamer port
    convert_to_meters=True,      # Convert mm to meters (default: True)
    verbose=False,               # Enable debug logging
    stale_data_timeout=3.0,      # Max time before data considered stale
    reconnect_delay=2.0          # Delay between reconnection attempts
)

# Start receiving data in background thread
listener.start()

# Get latest positions for all tracked objects
try:
    positions = listener.get_latest(check_connection=True)
    # Returns: {"TB10": (1.234, 2.345, 0.056), "REF1": (0.0, 0.0, 0.0)}
    
    for subject_name, (x, y, z) in positions.items():
        print(f"{subject_name}: x={x:.3f}m, y={y:.3f}m, z={z:.3f}m")
except ListenerConnectionError as e:
    print(f"Connection error: {e}")

# Check connection status
if listener.connected:
    print("Receiving fresh data")

# Stop listener when done
listener.stop()
```

**API Methods:**
- `start()`: Start background listener thread
- `stop()`: Stop listener and close connection
- `get_latest(check_connection=False)`: Get positions dict for all tracked subjects
  - Returns: `Dict[str, Tuple[float, float, float]]` - subject name → (x, y, z)
  - Units: meters (if `convert_to_meters=True`) or millimeters
  - Raises `ListenerConnectionError` if `check_connection=True` and data is stale
- `connected`: Property indicating if data is fresh (updated within timeout)

## Data Format

The streamer broadcasts JSON-formatted messages over TCP, newline-delimited:

```json
{
  "timestamp": 1706342400.123,
  "frame_number": 12345,
  "latency_ms": 2.5,
  "subject_count": 2,
  "subjects": [
    {
      "name": "TurtleBot1",
      "quality": 0.95,
      "segments": [
        {
          "name": "Base",
          "position": {
            "x": 1.234,
            "y": 2.345,
            "z": 0.056,
            "occluded": false
          },
          "orientation": {
            "x": 0.0,
            "y": 0.0,
            "z": 0.707,
            "w": 0.707,
            "occluded": false
          },
          "euler_xyz": {
            "x": 0.0,
            "y": 0.0,
            "z": 90.0,
            "occluded": false
          }
        }
      ],
      "markers": [
        {
          "name": "Marker1",
          "parent_segment": "Base",
          "position": {"x": 1.2, "y": 2.3, "z": 0.1},
          "occluded": false
        }
      ]
    }
  ]
}
```

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  Vicon System   │ ─────>  │  data_streamer   │ ─────>  │  data_listener  │
│  (localhost:801)│         │  (port 5555)     │         │  (any machine)  │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                     │
                                     ├─────>  Client 2
                                     ├─────>  Client 3
                                     └─────>  Client N
```

## Coordinate System

DataStream returns positions as *(x, y, z)* tuples in millimeters.

The coordinate system is configured as:
- **X-axis**: Forward
- **Y-axis**: Left
- **Z-axis**: Up (right-handed coordinate system)

Orientation is provided as:
- **Quaternion** (x, y, z, w) - most compact
- **Euler angles** (X, Y, Z) in degrees - most intuitive

## Requirements

### Windows Platform Software
1. Git
2. Tailscale (for remote access)
3. Vicon DataStream SDK

### Python Dependencies
- `vicon_dssdk` (Vicon DataStream SDK)
- Standard library only (no additional packages required)


### Using the System

An internal document (requires login) on using the system is available [here](https://sotonac-my.sharepoint.com/:b:/g/personal/aoa1v22_soton_ac_uk/IQDQhUJlGf75S63_iGKqfW0SAWEgIa8ja6rCAN2EURyvfEA?e=E3QLjA)