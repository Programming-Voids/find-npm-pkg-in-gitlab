#!/usr/bin/env python3
"""Integration tests for findings manager with scanner."""

import json
import os
import tempfile
from pathlib import Path

from src.findings_manager import FindingsManager, Finding
from src.scanner import scan_file
from src.utils import MatchRule


def test_findings_manager_initialization():
    """Test FindingsManager initialization and file creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        findings_file = os.path.join(tmpdir, "findings.json")
        manager = FindingsManager(findings_file)
        
        # Should not have created file yet (no findings added)
        assert not os.path.exists(findings_file)
        
        # Add a finding
        manager.add_finding(
            project="test-project",
            project_url="https://example.com/test",
            branch="main",
            file="package.json",
            file_type="npm",
            package="lodash",
            version="4.17.21",
            matched_rules=["exact:4.17.21"],
            matched_text='  "lodash": "4.17.21"'
        )
        
        # File should now exist
        assert os.path.exists(findings_file)
        
        # Verify file contents (JSONL format - one JSON per line)
        with open(findings_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data['package'] == 'lodash'
        assert data['version'] == '4.17.21'
        assert manager.findings_count == 1


def test_findings_manager_multiple_findings():
    """Test adding multiple findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        findings_file = os.path.join(tmpdir, "findings.json")
        manager = FindingsManager(findings_file)
        
        # Add multiple findings
        for i in range(3):
            manager.add_finding(
                project=f"project-{i}",
                project_url=f"https://example.com/project-{i}",
                branch="main",
                file=f"file-{i}.json",
                file_type="npm",
                package=f"package-{i}",
                version=f"1.0.{i}",
                matched_rules=[f"exact:1.0.{i}"],
                matched_text=f'Package {i} at version 1.0.{i}'
            )
        
        # Verify all findings were added (JSONL format - one per line)
        with open(findings_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 3
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data['package'] == f'package-{i}'
            assert data['version'] == f'1.0.{i}'
        
        # Check manager counts
        assert manager.findings_count == 3
        assert len(manager.packages_found) == 3


def test_findings_manager_load_existing():
    """Test loading existing findings from file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        findings_file = os.path.join(tmpdir, "findings.json")
        
        # Create first manager and add findings
        manager1 = FindingsManager(findings_file)
        manager1.add_finding(
            project="test",
            project_url="https://example.com/test",
            branch="main",
            file="package.json",
            file_type="npm",
            package="lodash",
            version="4.17.21",
            matched_rules=["exact:4.17.21"],
            matched_text="lodash@4.17.21"
        )
        
        # Create second manager and load existing metadata
        manager2 = FindingsManager(findings_file)
        assert manager2.findings_count == 1
        assert 'lodash' in manager2.packages_found
        
        # Add new finding to second manager
        manager2.add_finding(
            project="test2",
            project_url="https://example.com/test2",
            branch="develop",
            file="package2.json",
            file_type="npm",
            package="axios",
            version="1.4.0",
            matched_rules=["exact:1.4.0"],
            matched_text="axios@1.4.0"
        )
        
        # Verify both findings are in file
        with open(findings_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 2
        assert manager2.findings_count == 2
        assert 'lodash' in manager2.packages_found
        assert 'axios' in manager2.packages_found


def test_findings_with_scanner_integration():
    """Test that scanner results include matched_text."""
    package_lock_content = '''{
  "name": "test",
  "version": "1.0.0",
  "lockfileVersion": 2,
  "packages": {
    "": {
      "dependencies": {
        "lodash": "4.17.21"
      }
    },
    "node_modules/lodash": {
      "version": "4.17.21",
      "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz"
    }
  }
}'''
    
    rule = MatchRule(packages=["lodash"], exact_versions=["4.17.21"], version_ranges=[])
    compiled_ranges = []
    
    hits = scan_file(package_lock_content, "package-lock.json", rule, compiled_ranges)
    
    # Should find the package
    assert len(hits) > 0
    
    # Check that matched_text is populated
    for hit in hits:
        assert "matched_text" in hit
        if hit["matched_text"]:
            assert len(hit["matched_text"]) > 0


def test_findings_summary():
    """Test findings summary generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        findings_file = os.path.join(tmpdir, "findings.json")
        manager = FindingsManager(findings_file)
        
        # Add findings from multiple projects and files
        manager.add_finding(
            project="project-a",
            project_url="https://example.com/a",
            branch="main",
            file="package.json",
            file_type="npm",
            package="lodash",
            version="4.17.21",
            matched_rules=["exact:4.17.21"],
            matched_text="lodash@4.17.21"
        )
        
        manager.add_finding(
            project="project-a",
            project_url="https://example.com/a",
            branch="develop",
            file="package.json",
            file_type="npm",
            package="axios",
            version="1.4.0",
            matched_rules=["exact:1.4.0"],
            matched_text="axios@1.4.0"
        )
        
        manager.add_finding(
            project="project-b",
            project_url="https://example.com/b",
            branch="main",
            file="package-lock.json",
            file_type="npm",
            package="lodash",
            version="4.17.21",
            matched_rules=["exact:4.17.21"],
            matched_text="lodash@4.17.21"
        )
        
        summary = manager.get_summary()
        
        assert summary['total_findings'] == 3
        assert summary['unique_packages'] == 2  # lodash and axios
        assert summary['projects_with_findings'] == 2
        assert summary['files_with_findings'] == 3
        assert set(summary['packages']) == {'axios', 'lodash'}


if __name__ == "__main__":
    test_findings_manager_initialization()
    test_findings_manager_multiple_findings()
    test_findings_manager_load_existing()
    test_findings_with_scanner_integration()
    test_findings_summary()
    print("✓ All integration tests passed!")
