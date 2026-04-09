"""
Findings manager for real-time tracking and live updates of discovered packages.
Maintains a live findings file that updates as scan progresses.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .utils import LOGGER


@dataclass
class Finding:
    """A single finding record with matched text."""
    
    timestamp: str
    project: str
    project_url: str
    branch: str
    file: str
    file_type: str
    package: str
    version: str
    matched_rules: List[str]
    matched_text: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class FindingsManager:
    """Manages live findings file and findings tracking.
    
    Uses append-only JSONL format to minimize memory usage.
    Tracks only metadata (count, unique packages) in memory.
    """
    
    def __init__(self, findings_file: str):
        """Initialize findings manager.
        
        Args:
            findings_file: Path to live findings JSONL file
        """
        self.findings_file = findings_file
        # Track only metadata in memory to keep footprint low
        self.findings_count = 0
        self.packages_found: set = set()
        self.files_with_findings: set = set()
        self.projects_with_findings: set = set()
        
        # Try to load existing metadata if file exists
        if os.path.exists(findings_file):
            self._load_existing_metadata()
    
    def _load_existing_metadata(self) -> None:
        """Load existing findings metadata from JSONL file.
        
        Only scans file for metadata (counts), doesn't load full findings into memory.
        """
        try:
            with open(self.findings_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        self.findings_count += 1
                        self.packages_found.add(data.get('package', ''))
                        file_key = f"{data.get('project', '')}/{data.get('branch', '')}/{data.get('file', '')}"
                        self.files_with_findings.add(file_key)
                        self.projects_with_findings.add(data.get('project', ''))
                    except json.JSONDecodeError:
                        continue
            LOGGER.info("Loaded metadata from %d existing findings in %s", self.findings_count, self.findings_file)
        except Exception as exc:
            LOGGER.warning("Failed to load existing findings metadata from %s: %s", self.findings_file, exc)
            self.findings_count = 0
    
    def add_finding(
        self,
        project: str,
        project_url: str,
        branch: str,
        file: str,
        file_type: str,
        package: str,
        version: str,
        matched_rules: List[str],
        matched_text: Optional[str] = None,
    ) -> None:
        """Add a finding and append to file (JSONL format).
        
        Uses append-only writes to avoid rewriting entire file.
        Only metadata tracked in memory, not full findings.
        
        Args:
            project: Project name
            project_url: Project URL
            branch: Branch name
            file: File path in repository
            file_type: Type of file (detected format)
            package: Package name that was found
            version: Version that was found
            matched_rules: List of matching rules (exact:version, range:*, etc.)
            matched_text: The actual matched text from the file
        """
        finding = Finding(
            timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            project=project,
            project_url=project_url,
            branch=branch,
            file=file,
            file_type=file_type,
            package=package,
            version=version,
            matched_rules=matched_rules,
            matched_text=matched_text,
        )
        
        # Update metadata tracking (minimal memory overhead)
        self.findings_count += 1
        self.packages_found.add(package)
        file_key = f"{project}/{branch}/{file}"
        self.files_with_findings.add(file_key)
        self.projects_with_findings.add(project)
        
        # Append finding as JSON line (no rewrite of full file)
        self._append_finding(finding)
    
    def _append_finding(self, finding: Finding) -> None:
        """Append finding to JSONL file (single line, no rewrites).
        
        JSONL format (JSON Lines) allows append-only writes without
        rewriting the entire file. Each line is a complete JSON object.
        This is O(1) per finding instead of O(n).
        """
        try:
            with open(self.findings_file, 'a') as f:
                # Write as single JSON line (no pretty printing to save space)
                json.dump(finding.to_dict(), f, separators=(',', ':'))
                f.write('\n')  # Newline separates records
        except Exception as exc:
            LOGGER.error("Failed to append finding to %s: %s", self.findings_file, exc)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of findings from in-memory metadata.
        
        No file I/O required since metadata is tracked during add_finding().
        """
        return {
            'total_findings': self.findings_count,
            'unique_packages': len(self.packages_found),
            'files_with_findings': len(self.files_with_findings),
            'projects_with_findings': len(self.projects_with_findings),
            'packages': sorted(self.packages_found),
        }
    
    def clear(self) -> None:
        """Clear all findings metadata and delete file."""
        self.findings_count = 0
        self.packages_found.clear()
        self.files_with_findings.clear()
        self.projects_with_findings.clear()
        
        if os.path.exists(self.findings_file):
            try:
                os.remove(self.findings_file)
                LOGGER.info("Cleared findings file %s", self.findings_file)
            except Exception as exc:
                LOGGER.error("Failed to clear findings file %s: %s", self.findings_file, exc)
