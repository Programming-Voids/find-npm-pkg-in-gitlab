#!/usr/bin/env python3
"""
Launcher script for the package scanner that does not depend on the repository folder name.
This script looks for modules in the src/ subdirectory.
"""

import importlib
import os
import sys


def main() -> int:
    # Get the directory containing this script (project root)
    project_root = os.path.abspath(os.path.dirname(__file__))
    # Extract package name from folder name (works with any folder name format)
    package_name = os.path.basename(project_root)
    # Get parent directory to add to Python path for package discovery
    parent_dir = os.path.dirname(project_root)

    # Verify that the scanner module exists before attempting to import
    if not os.path.exists(os.path.join(project_root, "src", "gitlab_repo_scanner.py")):
        print("Could not find src/gitlab_repo_scanner.py in the current directory.", file=sys.stderr)
        return 1

    # Add parent directory to Python path to allow importing the package
    # This enables the script to work regardless of folder name
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # Dynamically import the scanner module from src subdirectory by package name
    # This avoids hard-coded import paths that depend on folder naming
    try:
        module = importlib.import_module(f"{package_name}.src.gitlab_repo_scanner")
    except Exception as exc:
        print(f"Failed to import scanner module: {exc}", file=sys.stderr)
        return 1

    # Call the main scanner function and return its exit code
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())