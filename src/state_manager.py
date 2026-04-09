"""
State management for scan checkpointing and resuming.
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .utils import LOGGER


@dataclass
class ScanState:
    """State of a scan session for checkpoint and resume.
    
    Minimal memory design: only stores completed project IDs and statistics,
    NOT full findings (those go to findings manager for disk storage).
    """
    
    timestamp: str
    search_terms: List[str]
    filenames: List[str]
    exact_versions: List[str]
    version_ranges: List[str]
    completed_project_ids: Set[int] = field(default_factory=set)
    total_matches: int = 0
    total_errors: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert set to list for JSON serialization
        data['completed_project_ids'] = list(self.completed_project_ids)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScanState":
        """Create from dictionary."""
        # Convert list back to set
        data['completed_project_ids'] = set(data.get('completed_project_ids', []))
        return cls(**data)


def save_state(state: ScanState, state_file: str) -> None:
    """Persist scan state to disk for resume functionality.

    This allows the scan to be interrupted and resumed later without
    re-scanning already completed projects. The state includes:
    - Completed project IDs
    - Current findings
    - Aggregate statistics
    - Scan configuration
    """
    try:
        with open(state_file, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)
        LOGGER.info("Scan state saved to %s", state_file)
    except Exception as exc:
        LOGGER.error("Failed to save state to %s: %s", state_file, exc)


def load_state(state_file: str) -> Optional[ScanState]:
    """Load previously saved scan state from disk.

    Returns None if no state file exists or if loading fails.
    This enables resume functionality by restoring:
    - Which projects were already scanned
    - Previous findings
    - Current statistics
    """
    if not os.path.exists(state_file):
        LOGGER.info("State file %s does not exist", state_file)
        return None
    
    try:
        with open(state_file, 'r') as f:
            data = json.load(f)
        state = ScanState.from_dict(data)
        LOGGER.info("Loaded state from %s with %s completed projects", state_file, len(state.completed_project_ids))
        return state
    except Exception as exc:
        LOGGER.error("Failed to load state from %s: %s", state_file, exc)
        return None


def clear_state(state_file: str) -> None:
    """Delete a state file.

    This is used to clean up after a completed scan or when
    starting a fresh scan without resume functionality.
    """
    if os.path.exists(state_file):
        try:
            os.remove(state_file)
            LOGGER.info("Cleared state file %s", state_file)
        except Exception as exc:
            LOGGER.error("Failed to clear state file %s: %s", state_file, exc)


def create_initial_state(
    search_terms: List[str],
    filenames: List[str],
    exact_versions: List[str],
    version_ranges: List[str],
) -> ScanState:
    """Create a new scan state for a fresh scan session.

    Initializes the state with the scan configuration and current timestamp.
    This state will be updated as projects are scanned and findings are discovered.
    """
    return ScanState(
        timestamp=datetime.now().isoformat(),
        search_terms=search_terms,
        filenames=filenames,
        exact_versions=exact_versions,
        version_ranges=version_ranges,
    )


def filter_completed_projects(
    projects: List[Dict[str, Any]],
    state: ScanState,
) -> List[Dict[str, Any]]:
    """Filter out projects that have already been completed.

    When resuming a scan, this function ensures we don't re-scan
    projects that were already processed in a previous run.
    Returns only the projects that still need to be scanned.
    """
    completed_ids = state.completed_project_ids
    remaining = [p for p in projects if p["id"] not in completed_ids]
    skipped = len(projects) - len(remaining)
    
    if skipped > 0:
        LOGGER.info("Resuming scan: skipping %s already-completed project(s)", skipped)
    
    return remaining


def update_state_with_result(state: ScanState, result: Dict[str, Any]) -> None:
    """Update scan state with results from a completed project scan.
    
    Only updates statistics and tracking IDs.
    Findings are handled separately by findings_manager (disk storage).
    """

    # Validate required keys (fail fast with clear message)
    required_keys = ["project_id", "error"]
    missing = [k for k in required_keys if k not in result]
    if missing:
        raise ValueError(f"Invalid result: missing keys {missing}")

    project_id = result["project_id"]

    # Mark this project as completed for resume functionality
    state.completed_project_ids.add(project_id)

    # Track match and error counts (not full findings)
    if result["findings"]:
        state.total_matches += sum(len(f["hits"]) for f in result["findings"])

    if result["error"]:
        state.total_errors += 1
