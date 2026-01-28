#Requires -Version 5.1
<#
.SYNOPSIS
    Uninstall Vicon DataStream convenience commands from PowerShell profile

.DESCRIPTION
    Removes vicon-env, vicon-stream, and vicon-listen commands
    along with their auto-completion from your PowerShell profile.
    
    Optionally removes the Python virtual environment.
    
    Does NOT remove:
    - The repository files

.EXAMPLE
    .\uninstall.ps1
    Remove vicon commands from profile

.EXAMPLE
    .\uninstall.ps1 -KeepBackup
    Remove commands but keep a backup of the original profile

.EXAMPLE
    .\uninstall.ps1 -RemoveEnv
    Remove commands and Python environment without prompting

.NOTES
    Safe to run multiple times - will only remove vicon commands if they exist
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [switch]$KeepBackup,
    
    [Parameter(Mandatory=$false)]
    [switch]$RemoveEnv
)

# Configuration
$ScriptPath = Split-Path -Parent $PSCommandPath
$RepoPath = Split-Path -Parent (Split-Path -Parent $ScriptPath)
$RepoName = Split-Path -Leaf $RepoPath
$EnvName = $RepoName
$EnvPath = "$HOME\envs\$EnvName"

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "$Message... " -NoNewline -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Yellow
}

# ============================================================================
# MAIN
# ============================================================================

Write-Host "`n=== Vicon Commands Uninstaller ===" -ForegroundColor Cyan
Write-Host ""

# Get profile path
$profilePath = $PROFILE.CurrentUserAllHosts
Write-Info "Profile path: $profilePath"

# Check if profile exists
if (!(Test-Path $profilePath)) {
    Write-Info "PowerShell profile doesn't exist - nothing to remove"
    exit 0
}

# Read profile content
Write-Step "Reading PowerShell profile"
try {
    $profileContent = Get-Content $profilePath -Raw
    Write-Host "[OK]" -ForegroundColor Green
} catch {
    Write-ErrorMsg "Failed to read profile: $_"
    exit 1
}

# Check if vicon commands exist
if ($profileContent -notlike "*# Vicon Commands*") {
    Write-Info "No Vicon commands found in profile - nothing to remove"
    exit 0
}

# Create backup if requested
if ($KeepBackup) {
    Write-Step "Creating profile backup"
    $backupPath = "$profilePath.vicon-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    try {
        Copy-Item $profilePath $backupPath
        Write-Host "[OK]" -ForegroundColor Green
        Write-Info "Backup saved to: $backupPath"
    } catch {
        Write-ErrorMsg "Failed to create backup: $_"
        exit 1
    }
}

# Remove vicon commands
Write-Step "Removing Vicon commands from profile"
try {
    # Remove everything from "# Vicon Commands" until the next blank line or end of file
    $updatedContent = $profileContent -replace '(?s)\r?\n?# Vicon Commands.*?(?=\r?\n\r?\n|\z)', ''
    
    # Clean up any trailing whitespace
    $updatedContent = $updatedContent.TrimEnd()
    
    # Write back to profile
    Set-Content -Path $profilePath -Value $updatedContent -NoNewline
    Write-Host "[OK]" -ForegroundColor Green
} catch {
    Write-ErrorMsg "Failed to update profile: $_"
    exit 1
}

Write-Host ""
Write-Success "Vicon commands removed successfully!"
Write-Host ""
Write-Info "The following commands have been removed:"
Write-Host "  - vicon-env" -ForegroundColor Yellow
Write-Host "  - vicon-stream" -ForegroundColor Yellow
Write-Host "  - vicon-listen" -ForegroundColor Yellow
Write-Host ""
Write-Info "To apply changes to your current session:"
Write-Host "  . `$PROFILE.CurrentUserAllHosts" -ForegroundColor Yellow
Write-Host ""
Write-Info "Or simply restart PowerShell"
Write-Host ""

if ($KeepBackup) {
    Write-Info "Original profile backed up to:"
    Write-Host "  $backupPath" -ForegroundColor Yellow
    Write-Host ""
}

# ============================================================================
# REMOVE PYTHON ENVIRONMENT
# ============================================================================

# Check if Python environment exists
if (Test-Path $EnvPath) {
    Write-Host ""
    Write-Info "Python environment found at: $EnvPath"
    
    if ($RemoveEnv) {
        $removeConfirmed = $true
    } else {
        $response = Read-Host "Remove Python environment? (y/N)"
        $removeConfirmed = $response -eq 'y' -or $response -eq 'Y'
    }
    
    if ($removeConfirmed) {
        Write-Step "Removing Python environment"
        try {
            Remove-Item $EnvPath -Recurse -Force
            Write-Host "[OK]" -ForegroundColor Green
            Write-Success "Python environment removed"
        } catch {
            Write-ErrorMsg "Failed to remove environment: $_"
            Write-Info "You may need to close any programs using the environment and try again"
        }
    } else {
        Write-Info "Keeping Python environment"
    }
    Write-Host ""
}
