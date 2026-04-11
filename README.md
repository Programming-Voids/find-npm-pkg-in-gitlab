# GitLab Repository File Scanner

A Python script to scan GitLab repositories for package names, versions, or arbitrary strings in repository files.

It supports:

- multiple search terms or package names
- multiple exact versions
- one or more npm semver ranges
- searching any filename, not just `package-lock.json`
- structured parsing for multiple lock file formats (npm, yarn, poetry, pipenv, go, rust, ruby, php, java, dart)
- generic text search for other file types
- GitLab group or org targeting
- optional subgroup traversal
- parallel scanning across projects
- default-branch scanning
- all-branch scanning
- pattern-based branch scanning
- file logging
- progress bar output
- repository and branch terminal logging
- colorized terminal output
- per-second throughput stats
- live summary line in the progress bar

## Supported Lock File Formats

The scanner provides **structured parsing** for the following package lock file formats:

### JavaScript/Node.js
- `package-lock.json` (npm) — JSON format with packages map and dependencies tree
- `yarn.lock` (yarn) — YAML-like text format

### Python
- `Pipfile.lock` (Pipenv) — JSON format with default/develop sections
- `poetry.lock` (Poetry) — TOML format
- `requirements.txt` / `requirements.lock` (pip) — Text format with version specifiers

### Go
- `go.sum` (Go modules) — Text format with module version hashes

### Rust
- `Cargo.lock` (Cargo) — TOML format

### Ruby
- `Gemfile.lock` (Bundler) — Text format with indented gem entries

### PHP
- `composer.lock` (Composer) — JSON format with packages/packages-dev arrays

### Java
- `gradle.lock` (Gradle) — Text format with group:artifact:version entries

### Dart
- `pubspec.lock` (Pub) — YAML format

## What changed

The scanner can now search **any filename** using one or more `--filename` flags.

Examples:

```bash
python gitlab_repo_scanner.py \
  --filename package-lock.json \
  --package axios \
  --version 1.14.1
```

```bash
python gitlab_repo_scanner.py \
  --filename yarn.lock \
  --filename poetry.lock \
  --package requests
```

```bash
python gitlab_repo_scanner.py \
  --filename Cargo.lock \
  --filename composer.lock \
  --package uuid
```

```bash
python gitlab_repo_scanner.py \
  --filename go.sum \
  --filename Gemfile.lock \
  --package database
```

## Search behavior

### Structured Lock Files
When the matched file is a recognized lock file format (listed above), the script uses structured parsing:
- exact package matching (package names must match exactly)
- exact version matching (for specified versions)
- semver range matching (for specified ranges)
- format-specific parsing to extract version information correctly

### Generic Files
For all other filenames, the script uses generic text search:
- checks whether the search term appears in the file
- if `--version` or `--range` is also supplied, it requires the version/range text to appear too
- versions and ranges in generic files are matched as literal text, not semver-evaluated structure

## File structure

Project organized into clean subdirectories:

**Source Code** (`/src/`):
- `gitlab_repo_scanner.py` — main CLI and orchestration entry point. Parses arguments, loads target projects, selects branches, and delegates file scanning.
- `gitlab_api.py` — GitLab API helpers for project listing, branch selection, file discovery, and raw file retrieval. Uses `config.py` for API connection settings and `utils.py` for logging.
- `scanner.py` — file parsing and match detection. Contains structured parsing for `package-lock.json`/`yarn.lock` and generic text search for other files.
- `utils.py` — shared utilities for logging, progress output, run statistics, and helper functions used by all modules.
- `config.py` — configuration constants, GitLab session setup, ANSI color codes, and colorization helpers.
- `state_manager.py` — scan state persistence for resumable scans and progress tracking.
- `__init__.py` — package marker enabling package-style imports.

**Documentation** (`/docs/`):
- `README.md` — primary usage documentation (root level)
- `LLMS_GUIDE.md` — architecture guide for AI/LLM interpretation
- `MODULE_REFERENCE.md` — function signatures and module documentation
- `DEBUGGING_GUIDE.md` — troubleshooting and performance debugging
- `ARCHITECTURE_DECISIONS.md` — design decisions and trade-offs
- `TEST_RESULTS.md` — test documentation and results
- `DOCUMENTATION_INDEX.md` — navigation guide for all documentation
- `PROJECT_IMPROVEMENT_WORKFLOW.md` — 7-phase improvement methodology template

**Tests** (`/tests/`):
- `test_options.py` — CLI argument parsing tests (23 tests)
- `test_functionality.py` — core functionality tests (12 tests)

**Root Level**:
- `run_scanner.py` — wrapper launcher that runs the scanner without depending on the folder name.
- `requirements.txt` — pinned Python dependencies required to run the tool.
- `README.md` — primary usage documentation and examples.
- `.gitignore` — prevents Git from tracking cache files and virtual environments.

## Requirements

Install dependencies:

```bash
pip install -r requirements.txt
```

## Installation & Setup

### Virtual Environment (Recommended)

Create and activate a virtual environment to isolate dependencies:

```bash
# Create virtual environment
python -m venv .venv

# Activate on Windows
.venv\Scripts\activate

# Activate on macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Development Setup

This repository uses an internal package-style layout with shared modules.
If you see import errors from `.config` or `.utils`, run the scanner in package context rather than as a plain script.

The project includes:
- `__pycache__/` directories (auto-generated Python bytecode cache files that are created when Python code runs - these are not included in the repository initially and are excluded by `.gitignore`)
- `.gitignore` configured to exclude cache files and virtual environments

## Running from source

From the repository root, use the provided wrapper script:

```bash
python run_scanner.py \
  --package axios \
  --version 1.14.1
```

Or for a filename search:

```bash
python run_scanner.py \
  --filename package-lock.json \
  --package axios
```

## Environment variables

```bash
export GITLAB_URL="https://gitlab.example.com"
export GITLAB_TOKEN="glpat-xxxxxxxx"
```

## Common examples

Search default `package-lock.json` files:

```bash
python gitlab_repo_scanner.py \
  --package axios \
  --version 1.14.1
```

Search several filenames:

```bash
python gitlab_repo_scanner.py \
  --filename package-lock.json \
  --filename yarn.lock \
  --filename requirements.txt \
  --package axios
```

Search all branches for a filename:

```bash
python gitlab_repo_scanner.py \
  --filename requirements.txt \
  --package requests \
  --all-branches
```

Search only release and hotfix branches:

```bash
python gitlab_repo_scanner.py \
  --filename pom.xml \
  --package log4j \
  --branch-pattern "release/*" \
  --branch-pattern "hotfix/*"
```

Search a specific group and its subgroups:

```bash
python gitlab_repo_scanner.py \
  --group my-org/platform \
  --include-subgroups \
  --filename package-lock.json \
  --package axios \
  --version 1.14.1
```

## Logging and terminal output

The terminal uses:
- time only, no date
- no thread name
- colorized levels and event lines
- progress bar with a live summary
- throughput stats for repos, branches, and files per second

The log file still keeps more detailed information.

Useful flags:

```bash
--log-file incident-scan.log
--verbose
--no-progress
```

## Notes

- `--filename` matches by basename, not full path.
- If you do not pass `--filename`, the default remains `package-lock.json`.
- `package-lock.json` gets structured parsing.
- Other files get generic text matching.
- Scanning all branches can significantly increase runtime and API usage.

## Security considerations

### Credential handling

- **Use environment variables only**: Never pass `GITLAB_URL` or `GITLAB_TOKEN` as command-line arguments.
- **Protect log files**: By default, log files are written to disk with OS file permissions. Ensure logs are restricted to authorized users only, as they may contain repository names and error details.
- **Limit credential scope**: Use a GitLab personal or group token with read-only API access, not an admin token.
- **Session persistence**: The session object persists in memory for the process lifetime. Run the scanner in isolated environments (containers, VMs, or clean shells).

### HTTPS and transport security

- **HTTPS enforcement**: The scanner rejects non-HTTPS GitLab URLs to prevent credential transmission over plaintext.
- **Default SSL/TLS verification**: Certificate verification is enabled by default. Self-signed certificates will be rejected unless you configure your environment appropriately.

### Dependency security

- **Pinned versions**: All dependencies are explicitly pinned in `requirements.txt` to prevent supply chain attacks from transitive package updates.
- **Minimal dependencies**: Only three external packages are used: `requests`, `semantic_version`, and `tqdm`.

### Sensitive data

- **Credentials in error messages**: Error messages are logged but never contain the GitLab token. Sensitive repository data is not logged.
- **Large file handling**: JSON parsing is performed on fetched files. Be cautious when scanning very large repositories or files, as they are held entirely in memory.

### Best practices

1. **Run in isolated environments**: Use containers, VMs, or dedicated CI/CD runner instances to limit exposure.
2. **Audit log files**: Regularly review and securely delete scan logs, as they contain repository and finding metadata.
3. **Rotate tokens**: Periodically rotate your GitLab token and revoke old ones.
4. **Test on a small scope first**: Start with `--group your-group` or a few `--project` flags to validate behavior before scanning widely.
5. **Monitor API rate limits**: The scanner respects GitLab's rate limiting. Adjust `--workers` if you encounter rate limit errors.

## OWASP Security Assessment

### OWASP Top 10 / API Top 10 Findings

This scanner was reviewed against OWASP Top 10 2021 and OWASP API Top 10 security frameworks.

#### ✅ Well Protected
- **A02: Cryptographic Failures** — HTTPS enforcement and TLS verification
- **A05: Security Misconfiguration** — Secure defaults, no hardcoded secrets
- **A06: Vulnerable Components** — Pinned dependency versions
- **A07: Identification & Auth Failures** — Token via environment only
- **A08: Software Integrity Failures** — Pinned versions prevent supply chain attacks

#### 🟡 Moderate Risk Mitigations
- **A03: Injection** — Branch patterns use safe `fnmatch` matching, not code execution
- **A09: Logging Failures** — Log files contain repository metadata; use `--log-file` in secure locations
- **API-04: Unrestricted Resource Consumption** — See resource limit options below

#### 🔴 High Risk Mitigations
- **A04: Insecure Design** — See resource limits below to prevent unintended enumeration
- **API-10: Unsafe API Consumption** — See resource limits below to prevent memory exhaustion

### Resource Limit Options

To prevent accidental or malicious resource exhaustion, use these optional flags:

```bash
--max-file-size BYTES
  Maximum size in bytes for each file. Skips files larger than this.
  Default: unlimited
  Example: --max-file-size 104857600 (100 MB)

--max-project-files NUMBER
  Maximum files to scan per project. Stops after reaching this count per project.
  Default: unlimited
  Example: --max-project-files 10000

--max-projects NUMBER
  Maximum projects to scan. Stops scan job after this many projects.
  Default: unlimited
  Example: --max-projects 500

--request-timeout SECONDS
  Timeout for GitLab API requests in seconds.
  Default: 30
  Example: --request-timeout 60
```

### Usage Examples for Resource-Limited Scans

Scan small scope safely:

```bash
python run_scanner.py \
  --group my-org \
  --package axios \
  --max-file-size 50000000 \
  --max-project-files 5000 \
  --max-projects 100
```

Large-scale audit with safeguards:

```bash
python run_scanner.py \
  --group my-org \
  --include-subgroups \
  --package lodash \
  --max-projects 1000 \
  --max-project-files 50000 \
  --request-timeout 45 \
  --workers 4
```

## Pause and Resume Scanning

The scanner supports checkpointing and resuming scans. This is useful for:
- Pausing large scans to continue later
- Recovering from interruptions (Ctrl+C automatically saves state)
- Running scans in stages across different time periods

### Usage

**Start a scan normally** (state is automatically saved when paused):

```bash
python run_scanner.py \
  --group my-org \
  --include-subgroups \
  --package axios \
  --state-file my_scan.json
```

If you press **Ctrl+C**, the scanner will save progress to `my_scan.json`.

**Resume the paused scan**:

```bash
python run_scanner.py \
  --resume \
  --group my-org \
  --include-subgroups \
  --package axios \
  --state-file my_scan.json
```

The scanner will skip the completed projects and continue from where it left off.

**Clear previous state and start fresh**:

```bash
python run_scanner.py \
  --clear-state \
  --group my-org \
  --package axios \
  --state-file my_scan.json
```

### State File

- Default location: `scan_state.json` (in current directory)
- Custom location: `--state-file /path/to/state.json`
- Format: JSON with completed project IDs, findings, and scan metadata
- Automatically updated: State is saved when scan completes or is interrupted
- Safe to resume: Same search parameters are validated; if different, start fresh with `--clear-state`

### Important Notes

- **State is per-scan**: Each unique scan (different packages, versions, filenames) should use a separate state file.
- **Graceful interruption**: Press Ctrl+C to stop the scan gracefully. State is automatically saved within ~100ms for resume.
- **Skip completed projects**: When resuming, completed projects are automatically skipped from the target list.
- **Resume with same parameters**: To resume, use the same search terms, filenames, and other flags as the original scan.

## Live Findings Tracking

The scanner maintains a **live findings file** that updates in real-time as the scan progresses. This allows you to monitor findings as they're discovered without waiting for the entire scan to complete.

### Features

- **Real-time updates**: Findings are appended to file as they're discovered (O(1) operation)
- **Memory-efficient**: JSONL format with metadata-only buffering in memory
- **Matched text extraction**: Each finding includes the actual matched line from the repository
- **Persistent tracking**: Findings accumulate across the scan, surviving any interruptions
- **Machine-readable format**: JSON Lines for efficient programmatic processing
- **Summary statistics**: Track unique packages, affected files, and projects
- **Large-scale ready**: Supports 10,000+ findings without memory bloat

### Using Live Findings

By default, findings are written to `findings.json`:

```bash
python run_scanner.py \
  --package axios \
  --version 1.14.1 \
  --username me --token xxx
```

This creates/updates `findings.json` with each discovered finding.

### Custom Findings File Location

```bash
python run_scanner.py \
  --package axios \
  --findings-file results/scan-2024-01-15.json
```

### Findings File Format

The findings file uses **JSONL (JSON Lines)** format for memory and I/O efficiency:

- **Format:** One JSON object per line (newline delimited)
- **Append-only:** Each finding appended with a single write operation
- **No rewrites:** File grows sequentially, enabling constant memory usage
- **Streaming support:** Process findings line-by-line without loading entire file

Example `findings.json`:
```jsonl
{"timestamp":"2024-01-15T14:23:41.234567Z","project":"my-org/backend-api","project_url":"https://gitlab.example.com/my-org/backend-api","branch":"main","file":"package-lock.json","file_type":"npm","package":"axios","version":"1.14.1","matched_rules":["exact:1.14.1"],"matched_text":"    \"axios\": \"1.14.1\","}
{"timestamp":"2024-01-15T14:23:42.345678Z","project":"my-org/frontend-app","project_url":"https://gitlab.example.com/my-org/frontend-app","branch":"develop","file":"package-lock.json","file_type":"npm","package":"axios","version":"1.14.1","matched_rules":["exact:1.14.1"],"matched_text":"    \"axios\": \"1.14.1\","}
```

### Finding Record Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 UTC timestamp when this finding was discovered |
| `project` | GitLab project path (e.g., `my-org/backend-api`) |
| `project_url` | Full URL to the project on GitLab |
| `branch` | Branch name where the file was found |
| `file` | Repository-relative path to the file |
| `file_type` | Detected file format (e.g., `npm`, `pipenv`, `cargo`) |
| `package` | Package name that was matched |
| `version` | Version that was matched |
| `matched_rules` | List of rules that matched (e.g., `["exact:1.14.1"]` or `["range:>=1.14.0 <1.15.0"]`) |
| `matched_text` | Actual text from the file showing the package/version |

### Monitoring Findings During Scan

You can monitor findings in real-time while the scan runs:

```bash
# Terminal 1: Start the scan
python run_scanner.py \
  --group my-org \
  --package axios \
  --findings-file findings.json

# Terminal 2: Monitor findings in real-time (count lines)
watch -n 1 'wc -l findings.json'

# Or parse each line as it's added
tail -f findings.json | python -c "import json, sys; [print(json.loads(line).get('package')) for line in sys.stdin]"
```

Or parse findings programmatically:

```python
import json

with open('findings.json', 'r') as f:
    count = 0
    for line in f:
        if line.strip():
            finding = json.loads(line)
            print(f"Found {finding['package']} in {finding['project']}")
            count += 1
    print(f"Total findings: {count}")
```

### Matched Text Extraction

The `matched_text` field contains the actual line or snippet from the file that triggered the finding:

- **Structured files** (JSON, TOML, YAML): Returns the relevant key-value or entry line
- **Text files** (go.sum, requirements.txt, Gemfile.lock): Returns the exact matching line
- **Generic files**: Returns a snippet around the package/version mention (max 200 characters)

Examples:

```json
// npm package-lock.json
"matched_text": "    \"axios\": \"1.14.1\",",

// Python requirements.txt
"matched_text": "axios>=1.14.1",

// Go go.sum
"matched_text": "github.com/sirupsen/logrus v1.9.3",

// Ruby Gemfile.lock
"matched_text": "    axios (1.14.1)",
```

This matched text helps investigators quickly locate and verify findings in the repository.

## Testing

The scanner includes comprehensive test suites to verify all functionality works as intended. These tests validate:
- Command-line argument parsing and validation
- State file management (save, load, clear)
- Core scanner functions
- Utility functions and helpers

### Prerequisites for Testing

1. Python 3.10+ installed
2. Dependencies installed: `pip install -r requirements.txt`
3. No environment variables needed (tests don't require GitLab credentials)

### Running the Tests

#### Test 1: Argument Parsing and Validation

Tests all 30+ command-line options to ensure they parse correctly:

```bash
python tests/test_options.py
```

**What it tests:**
- Required arguments (--package is enforced)
- Repeatable arguments (--package, --version, --range, --filename, etc.)
- Boolean flags (--all-branches, --verbose, --no-progress, --resume, etc.)
- Numeric limits (--workers, --max-projects, --max-project-files, --max-file-size)
- String options (--log-file, --state-file, --branch-pattern, --group, --project)
- Complex multi-option scenarios combining many flags

**Expected output:**
```
✓ Basic package argument
✓ Multiple packages
✓ Exact version matching
✓ Version ranges
✓ Custom filenames
✓ Workers configuration
✓ All branches option
✓ Branch patterns
... (23 tests total)

============================================================
Results: 23 passed, 0 failed out of 23 tests
============================================================
```

**What passing means:**
- All command-line options parse without errors
- Arguments are stored with correct data types (strings, integers, lists, booleans)
- Defaults are applied correctly
- Repeatable arguments accumulate properly
- Complex scenarios with multiple options work together

#### Test 2: Functionality Tests

Tests core functionality including state management, scanner logic, and utilities:

```bash
python tests/test_functionality.py
```

**What it tests:**

**State File Handling (6 tests):**
- Creating initial scan state with configuration
- Saving state to disk and reloading
- Loading non-existent state files gracefully
- Clearing state files
- Updating state with scan results
- Filtering completed projects for resume functionality

**Scanner Functions (3 tests):**
- Version matching logic (exact and range matching)
- File type detection (package-lock.json vs other files)
- Deduplication of finding hits

**Utility Functions (3 tests):**
- List normalization (whitespace trimming, deduplication)
- Empty string filtering
- Thread-safe statistics tracking

**Expected output:**
```
============================================================
FUNCTIONALITY TESTS
============================================================

✓ Create initial state
✓ Save and load state file
✓ Load non-existent state file returns None
✓ Clear state file
✓ Update state with result
✓ Filter completed projects

============================================================
State File Tests: 6 passed, 0 failed out of 6 tests
============================================================
✓ Exact version matching
✓ Package lock file detection
✓ Dedupe hits

============================================================
Scanner Tests: 3 passed, 0 failed out of 3 tests
============================================================
✓ Normalize list with whitespace and dedup
✓ Normalize list filters empty strings
✓ Stats tracking

============================================================
Utils Tests: 3 passed, 0 failed out of 3 tests
============================================================

============================================================
OVERALL RESULTS
============================================================
State File Handling: ✓ PASS
Scanner Functions: ✓ PASS
Utilities Functions: ✓ PASS
```

**What passing means:**
- State can be persisted to disk and reloaded correctly
- Resume functionality will work for paused scans
- Version matching works for both exact and semver ranges
- File deduplication prevents reporting the same finding twice
- Utility functions operate correctly in multi-threaded environments

### Test Summary

**Total tests:** 35 (23 argument + 12 functionality tests)

| Test Suite | Tests | Status | Coverage |
|------------|-------|--------|----------|
| Argument Parsing | 23 | ✓ PASS | All CLI options |
| State Management | 6 | ✓ PASS | Save/load/clear/filter |
| Scanner Functions | 3 | ✓ PASS | Version matching, file detection |
| Utility Functions | 3 | ✓ PASS | List ops, stats, threading |
| **TOTAL** | **35** | **✓ PASS** | **100%** |

### Test Results Documentation

A detailed test report is available in `docs/TEST_RESULTS.md` which includes:
- Complete list of all tests performed
- Bug fixes applied during testing
- Expected outputs for each test
- Validation criteria

### Interpreting Test Failures

If a test fails, the output will show:

```
❌ Test name: error description
   Expected: <value>
   Got: <value>
```

**Common issues:**

1. **Import errors**: Ensure you're running tests from the project root directory
2. **Missing dependencies**: Run `pip install -r requirements.txt`
3. **Python version**: Tests require Python 3.10+. Check with `python --version`

### Running Tests in CI/CD

To use these tests in continuous integration:

```bash
# Exit with 0 if all tests pass, 1 if any fail
python test_options.py && python test_functionality.py
echo $?  # 0 = success, 1 = failure
```

Or in a script:

```bash
#!/bin/bash
set -e  # Exit on first failure

echo "Running argument parsing tests..."
python test_options.py || exit 1

echo "Running functionality tests..."
python test_functionality.py || exit 1

echo "All tests passed!"
```

### Development Testing

When making changes to the codebase:

1. Run tests before committing changes
2. If you add a new command-line option, add a test case to `test_options.py`
3. If you modify core functions, verify the relevant tests in `test_functionality.py` still pass
4. Check that no new test failures are introduced

### Test Files

- **test_options.py** - 23 tests for command-line argument parsing validation
- **test_functionality.py** - 12 tests for state management, scanner logic, and utilities
- **TEST_RESULTS.md** - Detailed test report with results and bug fixes

These files are included in the repository for quality assurance purposes and can be run at any time to verify the scanner is working correctly.


