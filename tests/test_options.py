#!/usr/bin/env python3
"""
Test script to validate all command-line options and their parsing.
Tests argument parsing without requiring GitLab credentials.
"""

import sys
import os
import argparse
from io import StringIO

# Add parent directory to path so we can import the package
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(parent_dir))

# Get package name from folder
package_name = os.path.basename(parent_dir)

def test_argument_parsing():
    """Test that all arguments parse correctly."""
    # Import parse_args from the package dynamically
    import importlib
    module = importlib.import_module(f"{package_name}.src.gitlab_repo_scanner")
    parse_args = module.parse_args
    
    tests = [
        # Test 1: Basic required argument
        {
            "args": ["--package", "axios"],
            "expected": {"packages": ["axios"], "workers": 8, "all_branches": False},
            "name": "Basic package argument"
        },
        # Test 2: Multiple packages
        {
            "args": ["--package", "axios", "--package", "lodash"],
            "expected": {"packages": ["axios", "lodash"]},
            "name": "Multiple packages"
        },
        # Test 3: Exact version matching
        {
            "args": ["--package", "axios", "--version", "1.0.0"],
            "expected": {"packages": ["axios"], "versions": ["1.0.0"]},
            "name": "Exact version matching"
        },
        # Test 4: Version ranges
        {
            "args": ["--package", "axios", "--range", ">=1.0.0 <2.0.0"],
            "expected": {"packages": ["axios"], "ranges": [">=1.0.0 <2.0.0"]},
            "name": "Version ranges"
        },
        # Test 5: Custom filenames
        {
            "args": ["--package", "axios", "--filename", "package.json", "--filename", "yarn.lock"],
            "expected": {"filenames": ["package.json", "yarn.lock"]},
            "name": "Custom filenames"
        },
        # Test 6: Workers configuration
        {
            "args": ["--package", "axios", "--workers", "16"],
            "expected": {"workers": 16},
            "name": "Workers configuration"
        },
        # Test 7: Branch options
        {
            "args": ["--package", "axios", "--all-branches"],
            "expected": {"all_branches": True},
            "name": "All branches option"
        },
        # Test 8: Branch patterns
        {
            "args": ["--package", "axios", "--branch-pattern", "release/*", "--branch-pattern", "main"],
            "expected": {"branch_patterns": ["release/*", "main"]},
            "name": "Branch patterns"
        },
        # Test 9: Log file configuration
        {
            "args": ["--package", "axios", "--log-file", "custom.log"],
            "expected": {"log_file": "custom.log"},
            "name": "Log file configuration"
        },
        # Test 10: Max projects limit
        {
            "args": ["--package", "axios", "--max-projects", "10"],
            "expected": {"max_projects": 10},
            "name": "Max projects limit"
        },
        # Test 11: Max project files limit
        {
            "args": ["--package", "axios", "--max-project-files", "100"],
            "expected": {"max_project_files": 100},
            "name": "Max project files limit"
        },
        # Test 12: Max file size limit
        {
            "args": ["--package", "axios", "--max-file-size", "1000000"],
            "expected": {"max_file_size": 1000000},
            "name": "Max file size limit"
        },
        # Test 13: Request timeout
        {
            "args": ["--package", "axios", "--request-timeout", "60"],
            "expected": {"request_timeout": 60},
            "name": "Request timeout configuration"
        },
        # Test 14: State file configuration
        {
            "args": ["--package", "axios", "--state-file", "my_state.json"],
            "expected": {"state_file": "my_state.json"},
            "name": "State file configuration"
        },
        # Test 15: Resume option
        {
            "args": ["--package", "axios", "--resume"],
            "expected": {"resume": True},
            "name": "Resume option"
        },
        # Test 16: Clear state option
        {
            "args": ["--package", "axios", "--clear-state"],
            "expected": {"clear_state": True},
            "name": "Clear state option"
        },
        # Test 17: Verbose logging
        {
            "args": ["--package", "axios", "--verbose"],
            "expected": {"verbose": True},
            "name": "Verbose logging"
        },
        # Test 18: No progress bar
        {
            "args": ["--package", "axios", "--no-progress"],
            "expected": {"no_progress": True},
            "name": "No progress bar"
        },
        # Test 19: Project filters
        {
            "args": ["--package", "axios", "--project", "backend", "--project", "frontend"],
            "expected": {"project_filters": ["backend", "frontend"]},
            "name": "Project filters"
        },
        # Test 20: Groups
        {
            "args": ["--package", "axios", "--group", "my-org"],
            "expected": {"groups": ["my-org"]},
            "name": "Group specification"
        },
        # Test 21: Include subgroups
        {
            "args": ["--package", "axios", "--group", "my-org", "--include-subgroups"],
            "expected": {"include_subgroups": True},
            "name": "Include subgroups"
        },
        # Test 22: Include archived
        {
            "args": ["--package", "axios", "--include-archived"],
            "expected": {"include_archived": True},
            "name": "Include archived projects"
        },
        # Test 23: Complex scenario with multiple options
        {
            "args": [
                "--package", "axios",
                "--package", "lodash",
                "--version", "1.0.0",
                "--version", "2.0.0",
                "--range", ">=1.0.0 <2.0.0",
                "--filename", "package-lock.json",
                "--filename", "yarn.lock",
                "--workers", "12",
                "--max-projects", "50",
                "--all-branches",
                "--verbose",
                "--no-progress",
            ],
            "expected": {
                "packages": ["axios", "lodash"],
                "versions": ["1.0.0", "2.0.0"],
                "ranges": [">=1.0.0 <2.0.0"],
                "filenames": ["package-lock.json", "yarn.lock"],
                "workers": 12,
                "max_projects": 50,
                "all_branches": True,
                "verbose": True,
                "no_progress": True,
            },
            "name": "Complex multi-option scenario"
        },
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        sys.argv = ["test_options.py"] + test["args"]
        try:
            args = parse_args()
            # Check expected values
            all_match = True
            for key, expected_value in test["expected"].items():
                actual_value = getattr(args, key)
                if actual_value != expected_value:
                    all_match = False
                    print(f"❌ {test['name']}: {key} mismatch")
                    print(f"   Expected: {expected_value}")
                    print(f"   Got: {actual_value}")
                    break
            
            if all_match:
                print(f"✓ {test['name']}")
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test['name']}: {e}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*60}")
    
    return failed == 0

if __name__ == "__main__":
    success = test_argument_parsing()
    sys.exit(0 if success else 1)
