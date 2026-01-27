#!/usr/bin/env python3
"""
Generate Requirements File from Current Python Environment

Extracts all installed packages from the current Python environment
and saves them to a requirements.txt file in the same directory as this script.

Usage:
    python get_requirements.py
    python get_requirements.py --exclude vicon_dssdk
    python get_requirements.py --output custom_requirements.txt
"""

import subprocess
import sys
from pathlib import Path
import argparse


def get_installed_packages(exclude_packages=None):
    """
    Get list of installed packages using pip freeze.
    
    Args:
        exclude_packages: List of package names to exclude
        
    Returns:
        List of requirement strings
    """
    exclude_packages = exclude_packages or []
    exclude_packages_lower = [pkg.lower() for pkg in exclude_packages]
    
    try:
        # Run pip freeze to get installed packages
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=True
        )
        
        packages = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                # Extract package name (before == or @)
                pkg_name = line.split('==')[0].split('@')[0].strip().lower()
                
                # Skip excluded packages
                if pkg_name not in exclude_packages_lower:
                    packages.append(line.strip())
        
        return sorted(packages)
        
    except subprocess.CalledProcessError as e:
        print(f"Error running pip freeze: {e}")
        print(f"stderr: {e.stderr}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


def write_requirements(packages, output_path):
    """
    Write packages to requirements file.
    
    Args:
        packages: List of requirement strings
        output_path: Path to output file
    """
    try:
        with open(output_path, 'w') as f:
            f.write("# Python requirements\n")
            f.write("# Generated automatically - do not edit manually\n")
            f.write(f"# Python version: {sys.version.split()[0]}\n")
            f.write("\n")
            
            for package in packages:
                f.write(f"{package}\n")
        
        print(f"Successfully wrote {len(packages)} packages to {output_path}")
        return True
        
    except Exception as e:
        print(f"Error writing requirements file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate requirements.txt from current Python environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate requirements.txt in script directory
    python get_requirements.py
    
    # Exclude specific packages
    python get_requirements.py --exclude vicon_dssdk pkg2
    
    # Custom output file
    python get_requirements.py --output ../requirements.txt
    
    # Exclude and custom output
    python get_requirements.py --exclude vicon_dssdk --output prod_requirements.txt
        """
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="requirements.txt",
        help="Output filename (default: requirements.txt)"
    )
    
    parser.add_argument(
        "--exclude", "-e",
        nargs="+",
        default=["vicon_dssdk"],
        help="Package names to exclude from requirements (default: vicon_dssdk)"
    )
    
    parser.add_argument(
        "--no-version",
        action="store_true",
        help="Don't include version numbers (just package names)"
    )
    
    args = parser.parse_args()
    
    # Determine output path (relative to script location)
    script_dir = Path(__file__).parent
    output_path = script_dir / args.output
    
    # Check if in virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )
    
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")
    print(f"Virtual environment: {'Yes' if in_venv else 'No'}")
    if in_venv:
        print(f"Virtual env path: {sys.prefix}")
    print(f"Output file: {output_path}")
    
    if args.exclude:
        print(f"Excluding packages: {', '.join(args.exclude)}")
    
    print("\nCollecting installed packages...")
    
    # Get packages
    packages = get_installed_packages(exclude_packages=args.exclude)
    
    if not packages:
        print("No packages found or error occurred.")
        sys.exit(1)
    
    # Remove version numbers if requested
    if args.no_version:
        packages = [pkg.split('==')[0].split('@')[0] for pkg in packages]
    
    print(f"Found {len(packages)} packages")
    
    # Write to file
    success = write_requirements(packages, output_path)
    
    if success:
        print(f"\nRequirements saved to: {output_path.absolute()}")
        print("\nTo install in another environment:")
        print(f"  pip install -r {output_path.name}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
