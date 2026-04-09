# Documentation for AI/LLM Code Interpretation

This guide helps AI and LLM models understand the project structure, design patterns, and decision rationale.

## Quick Overview

**Project:** GitLab Package Scanner  
**Purpose:** Scan GitLab repositories for packages, versions, or arbitrary strings in files  
**Architecture:** Parallel processing with thread-safe state management  
**Key Tech:** Python 3.10+, REST API, parallel scanning, state persistence

---

## 1. 🏗️ Architecture & System Design

### High-Level Flow

```
User Input (CLI Args)
    ↓
Argument Validation & Environment Setup
    ↓
Project Discovery (GitLab API)
    ↓
Project Filtering & State Management
    ↓
Branch Selection per Project
    ↓
File Discovery per Branch
    ↓
Parallel File Scanning (ThreadPoolExecutor, max_workers=8 default)
    ↓
Result Aggregation & State Persistence
    ↓
Output & Final State Handling
```

### Key Design Decisions

**Why ThreadPoolExecutor?**
- Parallel project scanning is I/O bound (waiting for GitLab API responses)
- Thread pool allows 8 concurrent projects by default
- Threads = lower overhead than processes for I/O-bound work

**Why State Persistence?**
- Large scans can be interrupted (Ctrl+C)
- State allows resuming without re-scanning completed projects
- Tracks findings and statistics for reporting

**Why Separate Scanner & API Modules?**
- Clear separation of concerns
- GitLab API logic isolated in `gitlab_api.py`
- File parsing logic isolated in `scanner.py`
- Makes testing and maintenance easier

---

## 2. 📦 Module Dependencies & Relationships

```
run_scanner.py (Entry Point)
    └── gitlab_repo_scanner.py (Orchestration)
            ├── gitlab_api.py (API calls)
            │   ├── config.py (Session setup)
            │   └── utils.py (Logging)
            ├── scanner.py (File parsing)
            │   └── utils.py (Logging)
            ├── state_manager.py (State persistence)
            │   └── utils.py (Logging)
            └── utils.py (Shared utilities)
                └── config.py (Colors, locks)

config.py
    - GITLAB_URL, GITLAB_TOKEN (environment)
    - SESSION (requests.Session with auth headers)
    - PRINT_LOCK (threading.Lock for stdout)
    - ANSI color codes
```

---

## 3. 🔄 Data Flow

### Parallel Scan Process

```
Projects List [P1, P2, P3, P4, P5, P6, P7, P8]
    ↓
Thread Pool (8 workers) submits scan_project() tasks
    ↓
Each Worker:
    1. Selects branches for project
    2. For each branch:
        - Lists target files
        - For each file:
            - Fetches raw content
            - Determines file type
            - Parses (structured or generic)
            - Records matches
    3. Returns result dict
    ↓
as_completed() iterator processes results as finished
    ↓
For each result:
    - Extract findings
    - Update statistics (thread-safe with STATS_LOCK)
    - Update state (completed_project_ids)
    - Progress bar update
```

### Key Data Structures

**MatchRule** (utils.py)
```python
@dataclass
class MatchRule:
    packages: List[str]           # What to search for
    exact_versions: List[str]     # Exact version matches
    version_ranges: List[str]     # npm semver ranges
```

**ScanState** (state_manager.py)
```python
@dataclass
class ScanState:
    timestamp: str                          # When scan started
    search_terms: List[str]                # Original packages searched
    filenames: List[str]                  # Files scanned
    exact_versions: List[str]             # Exact versions
    version_ranges: List[str]             # Version ranges
    completed_project_ids: Set[int]       # For resume/filter
    findings: List[Dict[str, Any]]        # Results with findings
    total_matches: int                    # Total matches found
    total_errors: int                     # Errors encountered
```

---

## 4. 🔐 Threading & Concurrency Safety

### Thread Safety Mechanisms

**PRINT_LOCK** (config.py)
- Coordinates stdout/stderr writes from multiple threads
- Used by: `tqdm.write()`, `log_terminal_line()`
- Prevents garbled output when multiple threads print simultaneously

**STATS_LOCK** (utils.py)
- Protects `RUN_STATS` object during updates
- Used by: `update_stats()`, `get_stats_snapshot()`
- Ensures thread-safe statistics aggregation

**ThreadPoolExecutor Context Manager**
- Handles proper resource cleanup
- Waits for all tasks to complete before returning
- Prevents resource leaks

### Thread-Safe Operations

✓ `update_stats()` - Protected by STATS_LOCK  
✓ `log_terminal_line()` - Protected by PRINT_LOCK  
✓ `get_stats_snapshot()` - Protected by STATS_LOCK (returns copy)  
✓ `tqdm.write()` - Combined with PRINT_LOCK  
✓ Set operations on `completed_project_ids` - Set is atomic in CPython  
✓ List append to `findings` - Protected by state updates after parallel processing  

---

## 5. 🔧 Scanning Strategies by File Type

### Structured Lock Files (11 formats supported)

**package-lock.json / yarn.lock (npm ecosystem)**
```
Input: Raw JSON/YAML file content
    ↓
Parse as JSON/YAML
    ↓
Search "packages" map by path (node_modules/PACKAGE_NAME)
    ↓
Deep search "dependencies" tree recursively
    ↓
Version matching (exact or semver)
    ↓
Deduplicate hits
    ↓
Output: List of hit dicts with matched_rules
```

**Pipfile.lock (Pipenv/Python)**
```
Input: JSON with "default" and "develop" sections
    ↓
Parse each section separately
    ↓
Extract version from "version" field
    ↓
Strip version operators (==, >=, etc.)
    ↓
Version matching
    ↓
Output: Hits with section location info
```

**poetry.lock (Poetry/Python)**
```
Input: TOML format
    ↓
Parse TOML with toml library
    ↓
Iterate [[package]] entries
    ↓
Extract name and version fields
    ↓
Version matching
    ↓
Output: Hits from flat package list
```

**go.sum (Go modules)**
```
Input: Text format (module version hash lines)
    ↓
Split by lines, parse "module version hash" format
    ↓
Skip duplicates (go.sum has multiple entries per module)
    ↓
Version matching
    ↓
Output: Hits with module name and locked version
```

**Cargo.lock (Rust)**
```
Input: TOML format
    ↓
Parse with toml library
    ↓
Iterate [[package]] entries
    ↓
Extract name and version
    ↓
Version matching
    ↓
Output: Hits from flat package list
```

**composer.lock (PHP)**
```
Input: JSON with "packages" and "packages-dev" arrays
    ↓
Parse each array separately
    ↓
Extract name (vendor/package format) and version
    ↓
Match both full names and short names
    ↓
Version matching
    ↓
Output: Hits with section info
```

**Gemfile.lock (Ruby)**
```
Input: Text format with indented gem entries
    ↓
Parse lines looking for "gem-name (version)" pattern
    ↓
Extract version, remove operators
    ↓
Version matching
    ↓
Output: Hits from gem entries
```

**gradle.lock (Gradle/Java)**
```
Input: Text format with "group:artifact:requested=locked" entries
    ↓
Parse by splitting on "=" and ":"
    ↓
Extract artifact ID and locked version
    ↓
Version matching
    ↓
Output: Hits with artifact notation
```

**pubspec.lock (Dart)**
```
Input: YAML format with package entries
    ↓
Parse YAML with PyYAML library
    ↓
Iterate package keys
    ↓
Extract version field
    ↓
Version matching
    ↓
Output: Hits from YAML packages
```

**requirements.txt (pip/Python)**
```
Input: Text format with "package==version" lines
    ↓
Parse each line for package operators (==, >=, <=, ~=, etc.)
    ↓
Extract package name and version
    ↓
Handle multi-constraint lines (package>=1.0,<2.0)
    ↓
Version matching
    ↓
Output: Hits with extracted versions
```

**Format Detection Logic**
```python
get_lock_file_format(file_path):
    if endswith("package-lock.json"):
        return "package-lock.json"
    elif endswith("poetry.lock"):
        return "poetry.lock"
    ... (10 more checks)
    else:
        return None
```

**Common Capabilities Across All Parsers:**
- Exact version matching: "1.0.0" == "1.0.0"
- Semver range matching (where applicable): "1.0.0" matches ">=1.0.0 <2.0.0"
- Location/source tracking: Shows where package is found
- Deduplication: No duplicate results returned
- Error handling: Malformed input caught, returns []

### Generic Text Search (Fallback for unknown formats)

```
Input: Raw file content
    ↓
Search for package name as substring
    ↓
If versions/ranges specified:
    - Also require version/range text to appear
    - Versions matched as literal strings (not semver)
Else:
    - Package match alone is sufficient
    ↓
Output: List of hit dicts with text-based matched_rules
```

---

## 6. 📊 Performance Characteristics

### Complexity Analysis

**Overall:** O(projects * branches * files * search_terms)
- Mitigated by parallelization and limits (--max-projects, --max-project-files)

### Resource Usage

**Memory:**
- Entire file contents in memory during scanning
- State dict grows with findings
- Typical: 50-500MB for large scans

**Network:**
- All files fetched from GitLab API
- Rate-limited by GitLab (typically 10 req/sec)
- Respects GitLab rate limiting headers

---

## 7. 🎯 Key Functions to Understand

### Entry Points
- `run_scanner.py::main()` - Launcher, handles imports
- `gitlab_repo_scanner.py::main()` - Orchestration entry point

### Scanning Pipeline
- `gitlab_repo_scanner.py::scan_project()` - Scan single project
- `gitlab_repo_scanner.py::_scan_branch_files()` - Scan branch files
- `gitlab_repo_scanner.py::_scan_single_file()` - Dispatch to scanner

### Lock File Format Parsers
- `scanner.py::get_lock_file_format()` - Detect file format (11 formats)
- `scanner.py::parse_package_lock_json()` - npm package-lock.json
- `scanner.py::parse_yarn_lock()` - yarn.lock
- `scanner.py::parse_pipfile_lock()` - Pipenv Pipfile.lock
- `scanner.py::parse_poetry_lock()` - Poetry poetry.lock
- `scanner.py::parse_requirements_txt()` - pip requirements.txt
- `scanner.py::parse_go_sum()` - Go go.sum
- `scanner.py::parse_cargo_lock()` - Rust Cargo.lock
- `scanner.py::parse_gemfile_lock()` - Ruby Gemfile.lock
- `scanner.py::parse_composer_lock()` - PHP composer.lock
- `scanner.py::parse_gradle_lock()` - Gradle gradle.lock
- `scanner.py::parse_pubspec_lock()` - Dart pubspec.lock

### Version Matching & Utilities
- `scanner.py::version_matches()` - Check if version matches criteria
- `scanner.py::scan_structured_lock_file()` - Route to appropriate parser
- `scanner.py::scan_generic_file()` - Generic text search (fallback)

---

## 8. 🧩 Extension Points

### Adding Support for New Lock File Formats

**Architecture for adding a new format:**

1. **Create the parser function** in `scanner.py`:
```python
def parse_myformat_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Parse my-format and return matches."""
    hits: List[Dict[str, Any]] = []
    try:
        # Parse content (JSON, TOML, YAML, text, etc.)
        data = parse_content(content)
    except ParseError:
        LOGGER.warning("Skipped malformed my-format content.")
        return []
    
    # Extract packages and versions
    for package_name, version in extract_packages(data):
        if package_name not in rule.packages:
            continue
        
        matched, matched_rules = version_matches(
            version,
            rule.exact_versions,
            compiled_ranges,
        )
        
        if matched:
            hits.append({
                "package": package_name,
                "version": version,
                "location": "my-format.lock",
                "matched_rules": matched_rules,
                "source": "my-format.lock",
            })
    
    return dedupe_hits(hits)
```

2. **Add format detection** in `get_lock_file_format()`:
```python
elif file_path.endswith("my-format.lock"):
    return "my-format.lock"
```

3. **Register in LOCK_FILE_PARSERS**:
```python
LOCK_FILE_PARSERS["my-format.lock"] = parse_myformat_lock
```

4. **Add test cases** in `tests/test_lock_file_parsers.py`:
```python
def test_myformat_lock_parser():
    # Test 1: Parse valid format
    # Test 2: Parse multiple packages
    # Test 3: Verify error handling
```

### Adding New Version Matching Schemes

**To support new version operators or formats:**
1. Extend `version_matches()` logic in `scanner.py`
2. Add new `matched_rules` prefix (e.g., "pep440:", "ruby-gem:")
3. Create version parser: `def parse_version_pep440()`
4. Add test cases in `test_functionality.py`

---

## 9. 🚀 Performance Tuning

### For Large Scans (1000+ projects)

```bash
--workers 4              # Reduce to avoid rate limiting
--max-projects 100      # Scan in batches
--max-file-size 10000000 # Skip huge files
--request-timeout 60    # Increase timeout
```

### For Small Fast Scans

```bash
--workers 16            # Increase parallelism
--no-progress           # Skip progress bar overhead
```

---

## 10. 🧪 Testing Guide for LLMs

When working on this code:

1. **Syntax validation**
   - Run: `python -m py_compile src/*.py`
   - Catches import errors early

2. **Argument parsing tests**
   - Run: `python tests/test_options.py`
   - Tests all CLI options (23 tests)

3. **Core functionality tests**
   - Run: `python tests/test_functionality.py`
   - Tests state management, scanner, utilities (15 tests)

4. **Lock file parser tests**
   - Run: `python tests/test_lock_file_parsers.py`
   - Tests all 11 lock file formats (25 tests)
   - Tests state, scanner, utils (12 tests)

4. **Quick sanity check**
   - Run: `python run_scanner.py -h`
   - Verifies help works and no import errors
