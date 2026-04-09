# Module Reference Guide

Quick reference for all modules, their key functions, and signatures.

## 1. run_scanner.py

**Purpose:** Entry point wrapper that handles dynamic package imports (works with any folder name)

### Functions

#### `main() -> int`
- **Purpose:** Dynamically loads and executes the scanner
- **Returns:** Exit code (0 = success, 1 = failure)

---

## 2. gitlab_repo_scanner.py

**Purpose:** Main orchestration and CLI handling

### Main Entry Point

#### `main() -> int`
- **Purpose:** Orchestration entry point (execute scan from start to finish)
- **Returns:** Exit code (0 = no findings, 2 = findings found, 1 = error)

### Argument Parsing

#### `parse_args() -> argparse.Namespace`
- **Purpose:** Parse all CLI arguments
- **Returns:** Namespace with all argument values

### Scanning

#### `scan_project(...) -> Dict[str, Any]`
- **Purpose:** Scan entire project (all branches, all target files)
- **Returns:** Result dict with project info, scanned counts, findings, error

---

## 3. gitlab_api.py

**Purpose:** GitLab REST API interaction with rate limiting and pagination

### API Functions

#### `gitlab_get(url: str, params: Optional[Dict[str, Any]]) -> requests.Response`
- **Purpose:** Make authenticated GET request with rate limit handling
- **Rate Limiting:** If 429 (rate limited), extracts Retry-After header and retries
- **Returns:** Response object

#### `list_target_projects(...) -> List[Dict[str, Any]]`
- **Purpose:** Get target projects based on groups/membership
- **Returns:** List of project dicts

#### `select_branches_for_project(...) -> List[str]`
- **Purpose:** Select which branches to scan
- **Returns:** List of branch names

#### `list_target_files(...) -> List[str]`
- **Purpose:** List files in branch matching target filenames
- **Returns:** List of file paths

#### `get_file_raw(...) -> Optional[str]`
- **Purpose:** Fetch raw file content
- **Returns:** File content string or None if skipped

---

## 4. scanner.py

**Purpose:** File content parsing and match detection for multiple lock file formats

### Version Matching

#### `version_matches(installed_version: str, exact_versions: List[str], compiled_ranges: List) -> Tuple[bool, List[str]]`
- **Purpose:** Check if version matches any criteria
- **Returns:** (matched: bool, matched_rules: List[str])

### Structured Lock File Parsers

The scanner supports **11 different lock file formats** with dedicated parsers:

#### npm/Node.js Parsers
- `parse_package_lock_json(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `package-lock.json` with packages map and dependencies tree
  - Returns list of hits with package, version, location

- `parse_yarn_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `yarn.lock` YAML-like format
  - Returns list of hits

#### Python Parsers
- `parse_pipfile_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `Pipfile.lock` (Pipenv) with default/develop sections
  - Returns hits for both sections

- `parse_poetry_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `poetry.lock` (Poetry) in TOML format
  - Returns list of hits

- `parse_requirements_txt(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `requirements.txt` / `requirements.lock` with pip version specifiers (==, >=, <=, etc.)
  - Returns hits with extracted versions

#### Go Parser
- `parse_go_sum(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `go.sum` text format with module version hashes
  - Returns list of hits

#### Rust Parser
- `parse_cargo_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `Cargo.lock` TOML format
  - Returns list of hits

#### Ruby Parser
- `parse_gemfile_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `Gemfile.lock` text format with indented gem entries
  - Returns list of hits

#### PHP Parser
- `parse_composer_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `composer.lock` JSON format with packages/packages-dev arrays
  - Returns hits from both sections

#### Java Parser
- `parse_gradle_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `gradle.lock` text format with group:artifact:version entries
  - Returns list of hits

#### Dart Parser
- `parse_pubspec_lock(content: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
  - Parses `pubspec.lock` (Pub) in YAML format
  - Returns list of hits

### Lock File Format Detection

#### `get_lock_file_format(file_path: str) -> Optional[str]`
- **Purpose:** Determine lock file format based on filename
- **Returns:** Format name (e.g., 'package-lock.json', 'poetry.lock') or None for unknown formats
- **Formats Supported:** package-lock.json, yarn.lock, poetry.lock, Pipfile.lock, go.sum, Cargo.lock, composer.lock, Gemfile.lock, gradle.lock, pubspec.lock, requirements.txt

#### `should_parse_as_package_lock(file_path: str) -> bool`
- **Purpose:** Check if file should use structured parsing
- **Returns:** Boolean (True if known lock file format, False otherwise)

### Scan Functions

#### `scan_structured_lock_file(content: str, file_path: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
- **Purpose:** Route to appropriate parser based on file format
- **Fallback:** Generic text search if structured parsing fails or returns no hits
- **Returns:** List of hits

#### `scan_generic_file(content: str, rule: MatchRule) -> List[Dict[str, Any]]`
- **Purpose:** Generic text search for packages/versions (fallback for unknown formats)
- **Returns:** List of hits

#### `scan_file(content: str, file_path: str, rule: MatchRule, compiled_ranges: List) -> List[Dict[str, Any]]`
- **Purpose:** Main entry point - tries structured parsing first, falls back to generic search
- **Returns:** List of hits

---

## 5. state_manager.py

**Purpose:** Save/load/manage scan state for pause/resume

### State Class

#### `class ScanState(dataclass)`
```python
timestamp: str                  # ISO format timestamp
search_terms: List[str]         # Original --package values
completed_project_ids: Set[int] # Projects already scanned
findings: List[Dict]            # Detailed results
```

### Functions

#### `create_initial_state(...) -> ScanState`
- **Purpose:** Create fresh scan state
- **Returns:** New ScanState with empty results

#### `save_state(state: ScanState, state_file: str) -> None`
- **Purpose:** Persist state to JSON file

#### `load_state(state_file: str) -> Optional[ScanState]`
- **Purpose:** Load state from JSON file
- **Returns:** ScanState or None if file doesn't exist

#### `clear_state(state_file: str) -> None`
- **Purpose:** Delete state file

#### `update_state_with_result(state: ScanState, result: Dict) -> None`
- **Purpose:** Merge scan result into state

#### `filter_completed_projects(projects: List[Dict], state: ScanState) -> List[Dict]`
- **Purpose:** Remove completed projects from list
- **Returns:** Only projects not in completed_project_ids

---

## 6. findings_manager.py

**Purpose:** Real-time tracking and persistence of discovered findings during scan

### Finding Record Class

#### `class Finding(dataclass)`
```python
timestamp: str              # ISO 8601 UTC timestamp
project: str                # Project path (e.g., my-org/backend)
project_url: str            # Full GitLab project URL
branch: str                 # Branch name
file: str                   # File path in repository
file_type: str              # Format type (npm, poetry, cargo, etc.)
package: str                # Package name matched
version: str                # Version matched
matched_rules: List[str]    # Rules that matched (exact:1.0, range:>=1.0)
matched_text: Optional[str] # Actual text from file showing the finding
```

### Findings Manager Class

#### `class FindingsManager`

**Purpose:** Manage live findings file with append-only JSONL (JSON Lines) format for memory efficiency

#### `__init__(findings_file: str) -> None`
- **Purpose:** Initialize findings manager and load existing findings metadata
- **Parameters:**
  - `findings_file` - Path to JSONL file for storing findings
- **Behavior:** Scans existing findings file line-by-line for metadata (counts, unique packages) without loading full findings into memory
- **Memory:** Only metadata tracking (sets of packages, files, projects) kept in memory

#### `add_finding(...) -> None`
- **Purpose:** Add a finding and append to JSONL file (O(1) operation)
- **Parameters:**
  - `project: str` - Project name/path
  - `project_url: str` - Full project URL
  - `branch: str` - Branch name
  - `file: str` - File path in repository
  - `file_type: str` - Detected format (npm, pipenv, cargo, etc.)
  - `package: str` - Package name that matched
  - `version: str` - Package version
  - `matched_rules: List[str]` - Matching rules (e.g., `["exact:1.14.1"]`, `["range:>=1.0.0"]`)
  - `matched_text: Optional[str]` - Text snippet from file showing the match
- **Behavior:** Updates in-memory metadata, then appends single JSON line to file (no rewrites)
- **Performance:** O(1) per finding instead of O(n) file rewrite

#### `_append_finding(finding: Finding) -> None`
- **Purpose:** Append single finding to JSONL file (internal method)
- **Format:** JSONL (JSON Lines) - one JSON object per line
- **Separators:** Uses compact format (`separators=(',', ':')`) to minimize disk usage
- **Error Handling:** Logs errors to LOGGER without raising

#### `_load_existing_metadata() -> None`
- **Purpose:** Load metadata from existing JSONL file without loading full findings into memory
- **Behavior:** Scans file line-by-line, parses each JSON line, updates metadata sets (packages, files, projects)
- **Memory:** O(1) - only deduplicates and counts, doesn't store finding records
- **Error Handling:** Skips empty lines and logs parse errors without stopping

#### `get_summary() -> Dict[str, Any]`
- **Purpose:** Generate summary statistics from in-memory metadata
- **Returns:**
  ```python
  {
    'total_findings': int,        # Total findings discovered (from counter, no file scan)
    'unique_packages': int,       # Unique package names (from set)
    'files_with_findings': int,   # Number of distinct files (from set)
    'projects_with_findings': int,# Number of distinct projects (from set)
    'packages': List[str]         # Sorted list of package names (from set)
  }
  ```
- **Performance:** O(1) - no file I/O, only in-memory set operations

#### `clear() -> None`
- **Purpose:** Delete findings file and reset manager
- **Behavior:** Removes findings file from disk if it exists, resets all metadata

### Integration Points

**Called from:**
- `gitlab_repo_scanner.py::main()` - Initializes FindingsManager at scan start
- `gitlab_repo_scanner.py::_scan_single_file()` - Adds finding for each match discovered

**Findings file location:**
- Default: `findings.json` (current directory)
- Custom: Via `--findings-file` CLI argument

---

## 7. utils.py

**Purpose:** Shared utilities for logging, stats, CLI helpers

### Statistics

#### `update_stats(...) -> None`
- **Purpose:** Thread-safe stats update
- **Thread Safety:** Protected by STATS_LOCK

#### `get_stats_snapshot() -> dict`
- **Purpose:** Thread-safe stats read
- **Returns:** Deep copy of current stats

#### `format_live_summary(total_projects: int) -> str`
- **Purpose:** Format status line for progress bar
- **Returns:** String with statistics

### Logging

#### `setup_logging(log_file: str, verbose: bool) -> None`
- **Purpose:** Configure logging with file and console handlers

#### `log_terminal_line(message: str, color: Optional[str]) -> None`
- **Purpose:** Write colored message to terminal (thread-safe)

#### `fail(msg: str, code: int = 1) -> None`
- **Purpose:** Log error and exit program

### List Operations

#### `normalize_list(values: List[str]) -> List[str]`
- **Purpose:** Clean and deduplicate argument lists
- **Returns:** Cleaned list

### Globals

**`LOGGER`** - logging.Logger instance for all modules

**`PRINT_LOCK`** - threading.Lock for stdout/stderr serialization

---

## 7. config.py

**Purpose:** Configuration constants, session setup, colors

### Environment Variables

#### `GITLAB_URL`
- **Source:** `os.environ.get("GITLAB_URL")`
- **Validation:** Must be HTTPS URL

#### `GITLAB_TOKEN`
- **Source:** `os.environ.get("GITLAB_TOKEN")`
- **Usage:** Added to requests.Session headers

### Configuration

#### `REQUEST_TIMEOUT`
- **Type:** int (seconds)
- **Default:** 30

#### `SESSION`
- **Type:** requests.Session
- **Headers:** `{"PRIVATE-TOKEN": GITLAB_TOKEN}`

### Synchronization

#### `PRINT_LOCK`
- **Type:** threading.Lock
- **Purpose:** Serialize stdout writes

---

## Quick Function Lookup by Purpose

### "I want to scan a project"
- Entry: `gitlab_repo_scanner.py::main()`
- Per-project: `gitlab_repo_scanner.py::scan_project()`

### "I want to query the API"
- Projects: `gitlab_api.py::list_target_projects()`
- Branches: `gitlab_api.py::select_branches_for_project()`
- Files: `gitlab_api.py::list_target_files()`
- Content: `gitlab_api.py::get_file_raw()`

### "I want to parse a file"
- JSON: `scanner.py::scan_package_lock()`
- Any file: `scanner.py::scan_generic_file()`
- Version matching: `scanner.py::version_matches()`

### "I want to manage state"
- Create: `state_manager.py::create_initial_state()`
- Save: `state_manager.py::save_state()`
- Load: `state_manager.py::load_state()`
- Update: `state_manager.py::update_state_with_result()`

### "I want to track findings in real-time"
- Initialize: `findings_manager.py::FindingsManager(findings_file)`
- Add finding: `FindingsManager.add_finding(...)`
- Get summary: `FindingsManager.get_summary()`
- Findings output: Automatic JSON write to `findings_file`

### "I want to log something"
- To terminal: `utils.py::log_terminal_line()`
- To file: Use imported `LOGGER`
- Setup: `utils.py::setup_logging()`

### "I want thread-safe stats"
- Update: `utils.py::update_stats()`
- Read: `utils.py::get_stats_snapshot()`
- Format: `utils.py::format_live_summary()`
