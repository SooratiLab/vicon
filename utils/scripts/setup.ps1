#Requires -Version 5.1
<#
.SYNOPSIS
    Vicon DataStream Setup Script for Windows

.DESCRIPTION
    Automated setup script that:
    - Verifies required software is installed (Git, Python, Vicon SDK)
    - Clones/updates the repository
    - Creates Python virtual environment
    - Installs Vicon DataStream SDK in venv
    - Installs Python dependencies
    - Sets up convenience commands with auto-completion

.PARAMETER RepoUrl
    Git repository URL (default: auto-detect from current repo or prompt)

.EXAMPLE
    .\setup.ps1
    Run setup from current directory

.EXAMPLE
    .\setup.ps1 -RepoUrl https://github.com/your-org/vicon.git
    Specify custom repository URL

.NOTES
    Prerequisites (must be installed manually):
    - Git
    - Python 3.10+
    - Vicon DataStream SDK
    
    Works on Windows 10/11 with PowerShell 5.1+
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$RepoUrl = ""  # Auto-detect from current repo or prompt
)

# Configuration
# Dynamically determine repository path and name from script location
$ScriptPath = Split-Path -Parent $PSCommandPath
$RepoPath = Split-Path -Parent (Split-Path -Parent $ScriptPath)
$RepoName = Split-Path -Leaf $RepoPath

$EnvName = $RepoName
$EnvPath = "$HOME\envs\$EnvName"
$ViconSDKPath = "$env:ProgramFiles\Vicon\DataStream SDK\Win64\Python\vicon_dssdk"
$ErrorActionPreference = "Stop"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

function Write-Step {
    param([string]$Message)
    Write-Host "$Message... " -NoNewline -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Yellow
}

# ============================================================================
# VERIFICATION FUNCTIONS
# ============================================================================

function Test-Prerequisites {
    Write-Step "Checking Prerequisites"
    $hasErrors = $false
    $messages = @()
    
    # Check Git
    try {
        $gitVersion = git --version 2>&1
        if ($gitVersion -notmatch "git version") {
            $messages += "Git not working properly"
            $hasErrors = $true
        }
    } catch {
        $messages += "Git not found. Install from https://git-scm.com"
        $hasErrors = $true
    }
    
    # Check Python
    try {
        $pythonVersion = python --version 2>&1
        if ($pythonVersion -match "Python (\d+\.\d+)") {
            $version = $matches[1]
            if ([version]$version -lt [version]"3.10") {
                $messages += "Python $version is too old (need 3.10+)"
                $hasErrors = $true
            }
        } else {
            $messages += "Python not working properly"
            $hasErrors = $true
        }
    } catch {
        $messages += "Python not found. Install from https://python.org"
        $hasErrors = $true
    }
    
    # Check Vicon SDK
    if (!(Test-Path $ViconSDKPath)) {
        $messages += "Vicon SDK not found at: $ViconSDKPath"
        $hasErrors = $true
    }
    
    if ($hasErrors) {
        Write-Host "[ERROR]" -ForegroundColor Red
        foreach ($msg in $messages) {
            Write-Host "  - $msg" -ForegroundColor Red
        }
        exit 1
    }
    
    Write-Host "[OK]" -ForegroundColor Green
}

# ============================================================================
# REPOSITORY MANAGEMENT
# ============================================================================

function Get-RepositoryUrl {
    # If URL provided as parameter, use it
    if (![string]::IsNullOrWhiteSpace($RepoUrl)) {
        return $RepoUrl
    }
    
    # Try to detect from script location if in a git repo
    $scriptDir = Split-Path -Parent $PSCommandPath
    Push-Location $scriptDir
    try {
        $currentUrl = git config --get remote.origin.url 2>$null
        if ($currentUrl) {
            Pop-Location
            return $currentUrl
        }
    } catch {}
    Pop-Location
    
    # Use default public repository
    return "https://github.com/SooratiLab/vicon.git"
}

function Initialize-Repository {
    param([string]$Url)
    
    Write-Step "Setting Up Repository"
    
    if (Test-Path $RepoPath) {
        # Check if it's a git repository
        if (Test-Path "$RepoPath\.git") {
            Push-Location $RepoPath
            try {
                $beforeHash = git rev-parse HEAD 2>$null
                git fetch origin 2>&1 | Out-Null
                $pullOutput = git pull origin main 2>&1
                $afterHash = git rev-parse HEAD 2>$null
                
                if ($beforeHash -ne $afterHash) {
                    Write-Host "`n  Updated: $beforeHash -> $afterHash" -ForegroundColor Yellow
                }
            } catch {}
            Pop-Location
        } else {
            Write-Host "[ERROR]" -ForegroundColor Red
            Write-Host "  - Directory exists but is not a git repository: $RepoPath" -ForegroundColor Red
            exit 1
        }
    } else {
        $parentDir = Split-Path -Parent $RepoPath
        
        if (!(Test-Path $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }
        
        try {
            git clone $Url $RepoPath 2>&1 | Out-Null
        } catch {
            Write-Host "[ERROR]" -ForegroundColor Red
            Write-Host "  - Failed to clone repository: $_" -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host "[OK]" -ForegroundColor Green
}

# ============================================================================
# PYTHON ENVIRONMENT
# ============================================================================

function New-PythonEnvironment {
    Write-Step "Setting Up Python Environment"
    
    if (!(Test-Path $EnvPath)) {
        $envParent = Split-Path -Parent $EnvPath
        
        if (!(Test-Path $envParent)) {
            New-Item -ItemType Directory -Path $envParent -Force | Out-Null
        }
        
        try {
            python -m venv $EnvPath 2>&1 | Out-Null
        } catch {
            Write-Host "[ERROR]" -ForegroundColor Red
            Write-Host "  - Failed to create virtual environment: $_" -ForegroundColor Red
            exit 1
        }
    }
    
    # Upgrade pip to latest version
    $pythonExe = "$EnvPath\Scripts\python.exe"
    & $pythonExe -m pip install --upgrade pip 2>&1 | Out-Null
    
    Write-Host "[OK]" -ForegroundColor Green
}

function Install-ViconSDK {
    Write-Step "Installing Vicon SDK"
    
    $pythonExe = "$EnvPath\Scripts\python.exe"
    
    # Check if already installed
    $installed = & $pythonExe -m pip list 2>$null | Select-String "vicon.dssdk"
    if ($installed) {
        Write-Host "[OK]" -ForegroundColor Green
        return
    }
    
    if (!(Test-Path $ViconSDKPath)) {
        Write-Host "[ERROR]" -ForegroundColor Red
        Write-Host "  - Vicon SDK not found at: $ViconSDKPath" -ForegroundColor Red
        exit 1
    }
    
    # Copy SDK to user directory (avoids permission issues with Program Files)
    $userSDKPath = "$env:USERPROFILE\vicon_dssdk"
    if (!(Test-Path $userSDKPath)) {
        try {
            Copy-Item $ViconSDKPath $userSDKPath -Recurse -Force | Out-Null
        } catch {
            Write-Host "[ERROR]" -ForegroundColor Red
            Write-Host "  - Failed to copy SDK: $_" -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host ""  # Newline before output
    
    # Temporarily allow errors to be displayed
    $savedErrorPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    
    # Run pip install from user directory and show all output
    & $pythonExe -m pip install $userSDKPath
    $exitCode = $LASTEXITCODE
    
    # Restore error preference
    $ErrorActionPreference = $savedErrorPref
    
    Write-Host ""  # Newline after output
    
    if ($exitCode -ne 0) {
        Write-Host "[ERROR] Installation failed (exit code: $exitCode)" -ForegroundColor Red
        Write-Host "Try manually: python -m pip install '$userSDKPath'" -ForegroundColor Yellow
        exit 1
    }
    
    # Verify installation
    $installed = & $pythonExe -m pip list 2>$null | Select-String "vicon.dssdk"
    if (!$installed) {
        Write-Host "[ERROR]" -ForegroundColor Red
        Write-Host "  - Installation completed but package not found" -ForegroundColor Red
        exit 1
    }
    
    # Clean up: Delete SDK copy from user directory
    try {
        Remove-Item $userSDKPath -Recurse -Force -ErrorAction SilentlyContinue
    } catch {}
    
    Write-Host "Installing Vicon SDK... [OK]" -ForegroundColor Green
}

function Install-Dependencies {
    Write-Step "Installing Dependencies"
    
    $requirementsFile = "$RepoPath\utils\scripts\requirements.txt"
    $pythonExe = "$EnvPath\Scripts\python.exe"
    
    if (!(Test-Path $requirementsFile)) {
        Write-Host "[OK]" -ForegroundColor Green
        return
    }
    
    Write-Host ""  # Newline before output
    
    # Temporarily allow errors to be displayed
    $savedErrorPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    
    # Always run pip install to ensure dependencies are up to date
    & $pythonExe -m pip install -r $requirementsFile
    $exitCode = $LASTEXITCODE
    
    # Restore error preference
    $ErrorActionPreference = $savedErrorPref
    
    Write-Host ""  # Newline after output
    
    if ($exitCode -ne 0) {
        Write-Host "[ERROR] Installation failed (exit code: $exitCode)" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Installing Dependencies... [OK]" -ForegroundColor Green
}

# ============================================================================
# CONVENIENCE COMMANDS
# ============================================================================

function New-ConvenienceCommands {
    Write-Step "Setting Up Convenience Commands"
    
    $profilePath = $PROFILE.CurrentUserAllHosts
    $profileDir = Split-Path -Parent $profilePath
    
    # Create profile directory if it doesn't exist
    if (!(Test-Path $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }
    
    # Create profile file if it doesn't exist
    if (!(Test-Path $profilePath)) {
        New-Item -ItemType File -Path $profilePath -Force | Out-Null
    }
    
    # Check if commands already exist - look for vicon-env specifically
    $profileContent = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue
    if ($profileContent -like "*function vicon-env*") {
        Write-Host "[OK]" -ForegroundColor Green
        return
    }
    
    # If old commands exist without vicon-env, remove them first
    if ($profileContent -like "*# Vicon Commands*") {
        $profileContent = $profileContent -replace '(?s)# Vicon Commands.*?(?=\r?\n\r?\n|\z)', ''
        Set-Content -Path $profilePath -Value $profileContent.Trim()
    }
    
    # Add convenience commands to profile with auto-completion
    $commands = @"

# Vicon Commands
function vicon-env {
    `$activateScript = "$EnvPath\Scripts\Activate.ps1"
    if (Test-Path `$activateScript) {
        & `$activateScript
    } else {
        Write-Host "[ERROR] Virtual environment not found at: $EnvPath" -ForegroundColor Red
    }
}

function vicon-setup {
    `$setupScript = "$RepoPath\utils\scripts\setup.ps1"
    if (Test-Path `$setupScript) {
        & `$setupScript @args
    } else {
        Write-Host "[ERROR] Setup script not found at: `$setupScript" -ForegroundColor Red
    }
}

function vicon-stream {
    `$python = "$EnvPath\Scripts\python.exe"
    `$script = "$RepoPath\src\data_streamer.py"
    & `$python `$script `$args
}

function vicon-listen {
    `$python = "$EnvPath\Scripts\python.exe"
    `$script = "$RepoPath\src\data_listener.py"
    & `$python `$script `$args
}

# Auto-completion for vicon-env
Register-ArgumentCompleter -CommandName vicon-env -ScriptBlock {
    param(`$commandName, `$parameterName, `$wordToComplete, `$commandAst, `$fakeBoundParameters)
    @()  # No arguments needed
}

# Auto-completion for vicon-setup
Register-ArgumentCompleter -CommandName vicon-setup -ScriptBlock {
    param(`$commandName, `$parameterName, `$wordToComplete, `$commandAst, `$fakeBoundParameters)
    
    `$completions = @(
        [System.Management.Automation.CompletionResult]::new('-RepoUrl', '-RepoUrl', 'ParameterName', 'Git repository URL')
    )
    
    `$completions | Where-Object { `$_.CompletionText -like "`$wordToComplete*" }
}

# Auto-completion for vicon-stream
Register-ArgumentCompleter -CommandName vicon-stream -ScriptBlock {
    param(`$commandName, `$parameterName, `$wordToComplete, `$commandAst, `$fakeBoundParameters)
    
    `$completions = @(
        [System.Management.Automation.CompletionResult]::new('--host', '--host', 'ParameterName', 'Vicon Tracker host (default: localhost)'),
        [System.Management.Automation.CompletionResult]::new('--port', '--port', 'ParameterName', 'Vicon Tracker port (default: 801)'),
        [System.Management.Automation.CompletionResult]::new('--rate', '--rate', 'ParameterName', 'Streaming rate in Hz (default: 100)'),
        [System.Management.Automation.CompletionResult]::new('--pose', '--pose', 'ParameterName', 'Stream only position and orientation data'),
        [System.Management.Automation.CompletionResult]::new('--all', '--all', 'ParameterName', 'Stream all geometry data (segments + markers)'),
        [System.Management.Automation.CompletionResult]::new('--frames', '--frames', 'ParameterName', 'Include camera frame metadata'),
        [System.Management.Automation.CompletionResult]::new('--verbose', '--verbose', 'ParameterName', 'Enable verbose logging')
    )
    
    `$completions | Where-Object { `$_.CompletionText -like "`$wordToComplete*" }
}

# Auto-completion for vicon-listen
Register-ArgumentCompleter -CommandName vicon-listen -ScriptBlock {
    param(`$commandName, `$parameterName, `$wordToComplete, `$commandAst, `$fakeBoundParameters)
    
    `$completions = @(
        [System.Management.Automation.CompletionResult]::new('--host', '--host', 'ParameterName', 'Server host (default: localhost)'),
        [System.Management.Automation.CompletionResult]::new('--port', '--port', 'ParameterName', 'Server port (default: 5555)'),
        [System.Management.Automation.CompletionResult]::new('--save', '--save', 'ParameterName', 'Save data to CSV files'),
        [System.Management.Automation.CompletionResult]::new('--output', '--output', 'ParameterName', 'Output directory for CSV files'),
        [System.Management.Automation.CompletionResult]::new('--verbose', '--verbose', 'ParameterName', 'Enable verbose logging')
    )
    
    `$completions | Where-Object { `$_.CompletionText -like "`$wordToComplete*" }
}
"@
    
    Add-Content -Path $profilePath -Value $commands
    Write-Host "[OK]" -ForegroundColor Green
}

# ============================================================================
# VERIFICATION
# ============================================================================

function Test-Installation {
    Write-Step "Verifying Installation"
    
    $pythonExe = "$EnvPath\Scripts\python.exe"
    $errors = @()
    
    # Test Python environment
    try {
        $envPython = & $pythonExe --version 2>&1
        if (!$envPython) { $errors += "Python environment not working" }
    } catch {
        $errors += "Python environment not working"
    }
    
    # Test Vicon SDK import
    $testScript = "import vicon_dssdk"
    try {
        & $pythonExe -c $testScript 2>&1 | Out-Null
    } catch {
        $errors += "Failed to import Vicon SDK"
    }
    
    # Check if data_streamer exists
    if (!(Test-Path "$RepoPath\src\data_streamer.py")) {
        $errors += "data_streamer.py not found"
    }
    
    # Check if data_listener exists
    if (!(Test-Path "$RepoPath\src\data_listener.py")) {
        $errors += "data_listener.py not found"
    }
    
    if ($errors.Count -gt 0) {
        Write-Host "[ERROR]" -ForegroundColor Red
        foreach ($err in $errors) {
            Write-Host "  - $err" -ForegroundColor Red
        }
        exit 1
    }
    
    Write-Host "[OK]" -ForegroundColor Green
}

# ============================================================================
# FINAL INSTRUCTIONS
# ============================================================================

function Show-CompletionMessage {
    Write-Host "`nSetup completed successfully!" -ForegroundColor Green
    Write-Host "`nNext steps:"
    Write-Host "  1. Restart PowerShell"
    Write-Host "  2. Activate Environment: vicon-env"
    Write-Host "  3. Use commands: vicon-stream, vicon-listen"
    Write-Host "  4. Press TAB for auto-completion"
    Write-Host "`nAvailable commands:"
    Write-Host "  - vicon-env     : Activate Python environment"
    Write-Host "  - vicon-setup   : Re-run setup script"
    Write-Host "  - vicon-stream  : Start Vicon data streamer"
    Write-Host "  - vicon-listen  : Start Vicon data listener"
    Write-Host "`nDocumentation: $RepoPath\README.md`n"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

try {
    # Verify prerequisites
    Test-Prerequisites
    
    # Get repository URL and setup repo
    $repoUrl = Get-RepositoryUrl
    Initialize-Repository -Url $repoUrl
    
    # Create Python environment
    New-PythonEnvironment
    
    # Install Vicon SDK
    Install-ViconSDK
    
    # Install dependencies
    Install-Dependencies
    
    # Setup convenience commands
    New-ConvenienceCommands
    
    # Verify installation
    Test-Installation
    
    # Show completion message
    Show-CompletionMessage
    
} catch {
    Write-Host "`n[ERROR] Setup failed: $_`n" -ForegroundColor Red
    exit 1
}
