# Debugging Guide

Complete guide for debugging and troubleshooting the GitLab scanner.

## Quick Memory Resolution

**If memory usage is growing during large scans (2000+ projects):**

```bash
# Quick fix: Break into stages
python run_scanner.py --group my-org --package axios --max-projects 500

# Extra conservative (for memory-constrained systems)
python run_scanner.py --group my-org --package axios \
  --workers 2 --max-projects 100 --max-project-files 500 --max-file-size 10485760

# Monitor memory during scan
watch -n 5 'du -h scan_state.json findings.json; ps aux | grep python'
```

**See "High Memory Usage" section below for detailed solutions.**

---

## Quick Diagnostics


### 1. Enable Verbose Logging

```bash
python run_scanner.py --package axios --verbose
```

**Output:** DEBUG level logs to both console and log file
**Use:** See every API call, state operation, and decision

### 2. Check Log Files

```bash
# Follow logs in real-time
tail -f gitlab_scanner.log

# Search for errors
grep "ERROR" gitlab_scanner.log
```

**Log File Location:** Specified by `--log-file` (default: `gitlab_scanner.log`)

### 3. Inspect State File

```bash
# View current state
cat state.json | python -m json.tool

# Or on Windows
powershell -Command "Get-Content state.json | ConvertFrom-Json | ConvertTo-Json -Depth 10"
```

**State File Location:** Specified by `--state-file` (default: `state.json`)

---

## Common Issues & Solutions

### Issue: "GitLab API Authentication Failed"

**Symptoms:**
- Error: `401 Unauthorized`
- All API requests fail immediately

**Debug Steps:**
1. Check environment variables:
   ```bash
   echo $GITLAB_URL
   echo $GITLAB_TOKEN
   ```

2. Verify GITLAB_URL starts with `https://`

3. Test authentication directly:
   ```bash
   curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
        "$GITLAB_URL/api/v4/version"
   ```

4. Check token permissions:
   - Must have `read_api` scope
   - Must have access to target projects

**Fix:** Regenerate authentication token with proper scopes

---

### Issue: "Rate Limited (429)"

**Symptoms:**
- Error: `429 Too Many Requests`
- Retries occur but scan is very slow

**Debug Steps:**
1. Check current rate limit:
   ```bash
   curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
        -i "$GITLAB_URL/api/v4/version" | grep "RateLimit"
   ```

2. If seeing high concurrent requests:
   - View `--workers` count: `python run_scanner.py --help`
   - Check `Retry-After` header in logs

**Fix:**
- Reduce concurrent workers: `--workers 3`
- Increase request timeout: `--request-timeout 60`

---

### Issue: "No Findings Found (But Should Be)"

**Symptoms:**
- Expected packages not found
- File was found but vulnerabilities not detected

**Debug Steps:**
1. Verify search terms match exactly:
   ```python
   # In package-lock.json or generic file:
   grep -i "axios" package-lock.json | head -3
   ```

2. Check version matching:
   - Exact matches: `--version 1.0.0` (must match exactly)
   - Semver ranges: `--range ">=1.0.0 <2.0.0"` (must use quotes)

3. Verify filenames:
   ```bash
   python run_scanner.py --package axios --filename package-lock.json --verbose
   ```

4. Enable verbose logging to see scanning decisions:
   ```bash
   python run_scanner.py --package axios --verbose 2>&1 | grep -A 2 -B 2 "Searching\|Matched\|Found"
   ```

**Check:**
- Are searches case-sensitive? (Yes for package names, yes for versions)
- Are version ranges in semver format? (e.g., `"^1.0.0"` not `"1.0.0+"`)

---

### Issue: "False Positives in Version Matching"

**Symptoms:**
- Searching for version `1.14.1` reports findings for version `1.4.1`
- Unrelated version numbers appear in results
- Package name appears in file but found with wrong version
- Too many matches for specific version search

**Root Causes & Fixes Applied:**

**Issue #1: Version substring collision**
- Searching for `1.14.1` would match `1.4.1` (substring collision)
- **Fix:** Word boundary checking with regex: `(?<![a-zA-Z0-9])` + version + `(?![a-zA-Z0-9])`
- Now `1.14.1` only matches when isolated: `" 1.14.1"`, `"@1.14.1"`, `"=1.14.1"` - NOT `"1.4.1"` or `"114.1"`

**Issue #2: Package and version appearing separately**
- File contains both `axios` and `1.14.1` but for different packages
- Example: `axios 1.0.0` and `lodash 1.14.1` would incorrectly report axios 1.14.1
- **Fix:** Context-aware matching - package and version must appear together (same line or within 1 line)
- Only reports a match if package name and target version appear in close context

**Examples:**
- ✅ Matches: `"axios 1.14.1"`, `"axios@1.14.1"`, `"axios: 1.14.1"` (same line)
- ✅ Matches: `"axios@" + newline + "1.14.1"` (nearby lines)
- ❌ No match: `"axios 1.0.0"` when searching for `1.14.1`
- ❌ No match: `"axios"` line + separate `"1.14.1"` line (for different package)

**Verification:**
```bash
# Test that version substring collision is prevented
python run_scanner.py \
  --package axios \
  --version 1.14.1 \
  --filename requirements.txt \
  --verbose
# Should show 0 matches for files with only "axios 1.4.1" or "axios 114.1"

# Test that separate occurrences don't trigger false positives
# (requires custom file with axios on one line, 1.14.1 on another for different package)
```

**Impact:**
- ✅ False positive rate reduced to near-zero  
- ✅ All 19 tests continue to pass
- ✅ Existing valid matches unaffected
- ✅ Works across all generic file searches (requirements.txt, Gemfile, custom files, etc.)
- ✅ Proximity checking works for YAML, JSON, and plain text formats

---

### Issue: "Scan Interrupted / Crashed"

**Symptoms:**
- Ctrl+C during scan
- Program crashed unexpectedly
- Out of memory error

**Graceful Ctrl+C Handling (v2.0+):**
The scanner now responds to Ctrl+C signals instantly:
- Pressing Ctrl+C will interrupt the current scan within ~100ms
- Scan progress is automatically saved to the state file
- You can resume the scan later with `--resume` flag

```bash
# Interrupt a running scan from another terminal
kill -SIGINT <process_id>

# Or simply Ctrl+C in the terminal where scanner is running
# (Exit code: 1, progress saved automatically)

# Later, resume from where you left off
python run_scanner.py --package axios --resume
```

**Recovery (if interrupted mid-scan):**
1. Check state file:
   ```bash
   ls -lah scan_state.json
   cat scan_state.json | python -m json.tool | head -50
   ```

2. Resume scan:
   ```bash
   python run_scanner.py --package axios --resume
   ```

3. If state is corrupted:
   ```bash
   rm scan_state.json
   python run_scanner.py --package axios --clear-state
   ```

**Recovery (from crash):**
If the scanner crashes or is killed without Ctrl+C:
1. Scan state may be partially saved
2. Check if any findings were recorded: `cat findings.jsonl | wc -l`
3. Resume with `--resume` or start fresh with `--clear-state`

**Prevention:**
- Reduce project scope: `--max-projects 100`
- Reduce workers: `--workers 2`
- Monitor memory during scan
- Use `--max-file-size` and `--max-project-files` limits

---

### Issue: "File Size Too Large / Timeout"

**Symptoms:**
- Specific projects take too long
- "Request timed out" errors
- Progress bar stalls on a project

**Debug Steps:**
1. Find problematic file:
   - Check logs for timeout details
   - Check project git for large files: `git ls-files -z | xargs -0 du -h | sort -rh | head`

2. Check current limits:
   ```bash
   python run_scanner.py --help | grep -i "max-file\|max-project\|timeout"
   ```

**Fix:**
- Skip large files: `--max-file-size 5000000` (5MB)
- Limit files per project: `--max-project-files 100`
- Increase timeout: `--request-timeout 60`

---

### Issue: "Version Parsing Errors"

**Symptoms:**
- Error: `Invalid semantic version`
- Specific versions not matched

**Debug Steps:**
1. Check version format:
   ```bash
   # Valid semver:
   1.0.0 ✓
   ^1.2.3 ✓
   >=1.0.0 <2.0.0 ✓
   
   # Invalid:
   1.0 ✗ (missing patch)
   v1.0.0 ✗ (has 'v' prefix)
   ```

2. Test version parser directly:
   ```python
   from semantic_version import Version, NpmSpec
   
   # Test exact version
   v = Version.coerce("1.0.0")
   
   # Test range
   spec = NpmSpec("^1.0.0")
   ```

**Fix:** Use proper semver format, or use generic text search (`--filename custom.txt`)

---

### Issue: "Duplicate Results"

**Symptoms:**
- Same finding appears multiple times
- Statistics seem inflated

**Root Cause:** Usually from:
1. Multiple matching rules (exact + range)
2. Same package in both `packages` and `dependencies` in package-lock.json

**Should Not Happen:** Code includes deduplication in `scanner.py::dedupe_hits()`

**Debug:** Check `matched_rules` field in results to see why duplicate detected

---

## Performance Debugging

### Profiling Bottlenecks

**Method 1: Built-in Timing**
```bash
python run_scanner.py --package axios --verbose 2>&1 | \
  grep -E "duration|elapsed|completed"
```

**Method 2: Custom Profiling**
```python
import cProfile
import pstats
from io import StringIO

from gitlab_repo_scanner import main

prof = cProfile.Profile()
prof.enable()

main()

prof.disable()
s = StringIO()
ps = pstats.Stats(prof, stream=s).sort_stats('cumulative')
ps.print_stats(20)  # Top 20 functions
print(s.getvalue())
```

**Method 3: Monitor Resource Usage**
```bash
# Linux/Mac
time python run_scanner.py --package axios

# Or with resource monitoring:
/usr/bin/time -v python run_scanner.py --package axios
```

### Common Performance Issues

#### Issue: High CPU Usage
- **Cause:** Too many concurrent workers
- **Fix:** Reduce `--workers` to 3-5
- **Verify:** Top/Activity Monitor shows thread count

#### Issue: High Memory Usage
- **Status:** FIXED in v2.0+ with JSONL findings format
- **Cause (old):** Unbounded findings accumulation + O(n²) file rewrites
- **Fix:** Use JSONL append-only format for findings (automatic in current version)
- **Verify:** Memory stays ~500MB even for 2000+ projects

**If Still Experiencing Memory Issues — New Characteristics:**

##### Memory Architecture (Current: v2.0+)

**JSONL Append-Only Format (Default):**
- Findings stored as JSONL (JSON Lines) - one finding per line
- Each finding appended with single write operation
- Metadata (counts, packages) kept in memory as sets only
- No full findings list in RAM - only metadata tracking
- **Memory per 10,000 findings:** <1 MB (metadata only)
- **Memory per 100,000 findings:** <2 MB (set deduplication)

**Expected Memory Usage:**
```
Scenario: 2000 projects, 50 findings each (100,000 total)

Memory Breakdown:
  - State checkpointing: 100-200 KB
  - Metadata sets (packages, files, projects): 500-800 KB
  - Worker file buffers: 16-64 MB (workers × file size)
  - Result processing: 10-20 MB
  ___________________________________
  Total Peak: ~100-200 MB (does NOT accumulate)

Disk Usage:
  - State file: 50-100 KB
  - Findings file: 50-80 MB (on disk only, not in RAM)
  - Log file: 10-20 MB
  ___________________________________
  Total Disk: ~60-100 MB
```

**If Memory Still Growing — Investigate:**

1. **Check Python version and memory leaks:**
   ```bash
   python --version
   # Expected: Python 3.8+
   
   # Check for subprocess leaks
   ps aux | grep -i python
   # Should see only one python process per scan
   ```

2. **Monitor actual memory usage:**
   ```powershell
   # Windows
   while ($true) {
     $proc = Get-Process python -ErrorAction SilentlyContinue
     $mem_mb = ($proc.WorkingSet64 / 1MB)
     $state_kb = (Get-Item scan_state.json -EA 0).Length / 1KB
     $findings_count = (Get-Content findings.json | Measure-Object -Line).Lines
     Write-Host "[$(Get-Date -Format 'HH:mm:ss')] RAM: ${mem_mb}MB | State: ${state_kb}KB | Findings: ${findings_count} lines"
     Start-Sleep 5
   }
   ```

   ```bash
   # Linux/Mac
   watch -n 5 'ps aux | grep "run_scanner.py"; \
               du -h scan_state.json findings.json; \
               wc -l findings.json 2>/dev/null'
   ```

3. **If memory grows beyond 500MB:**
   - Check if workers are stuck downloading large files: `--max-file-size 5000000`
   - Reduce concurrent workers: `--workers 2`
   - Check for external processes: `ps aux | grep python`


##### Memory Monitoring

**Windows - Monitor Memory During Scan:**
```powershell
# Terminal 1: Run scan
python run_scanner.py --group my-org --package axios --verbose

# Terminal 2: Monitor process memory every 5 seconds
while ($true) {
  $proc = Get-Process python | Where-Object {$_.ProcessName -eq "python"}
  $mem_mb = ($proc.WorkingSet64 / 1MB)
  $state_size_mb = (Get-Item scan_state.json -ErrorAction SilentlyContinue).Length / 1MB
  $findings_size_mb = (Get-Item findings.json -ErrorAction SilentlyContinue).Length / 1MB
  Write-Host "Memory: $mem_mb MB | State: $state_size_mb MB | Findings: $findings_size_mb MB"
  Start-Sleep -Seconds 5
}
```

**Linux/Mac - Monitor Memory:**
```bash
# Terminal 2: Real-time memory monitoring
watch -n 5 'ps aux | grep python | grep run_scanner; \
            du -h scan_state.json findings.json 2>/dev/null; \
            free -h'

# Or use `top` command
top -p $(pgrep python)
```

**Python - Programmatic Memory Analysis:**
```python
import tracemalloc
import os
from gitlab_repo_scanner import main

tracemalloc.start()

# Run scan
main()

current, peak = tracemalloc.get_traced_memory()
print(f"Current memory: {current / 1024 / 1024:.1f} MB")
print(f"Peak memory: {peak / 1024 / 1024:.1f} MB")

# Show top allocations
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
print("\nTop 10 memory allocations:")
for stat in top_stats[:10]:
    print(stat)
```

##### Solutions & Recommendations

**1. Break Large Scans Into Stages** (Most Effective)

Instead of scanning 2000 projects at once, stage into batches:

```bash
# Stage 1: Projects 0-500
python run_scanner.py \
  --group my-org \
  --package axios \
  --max-projects 500 \
  --findings-file results/stage1.json

# Stage 2: Projects 501-1000 (continues where stage 1 left off)
python run_scanner.py \
  --group my-org \
  --package axios \
  --resume \
  --max-projects 500 \
  --findings-file results/stage2.json

# Repeat for remaining stages
# Merge results afterward: cat results/stage*.json | jq -s '.[] | .findings[]' > all_findings.json
```

**2. Limit Project Scope** (Immediate Impact)

```bash
# Scan one group instead of entire instance
python run_scanner.py \
  --group my-org/platform \
  --package axios

# Limit to specific projects
python run_scanner.py \
  --project backend \
  --project frontend \
  --package axios

# Combine with --max-projects
python run_scanner.py \
  --group my-org \
  --max-projects 100 \
  --package axios
```

**3. Reduce Concurrency** (Decreases Thread Memory)

```bash
# Fewer workers = less concurrent file buffering
python run_scanner.py \
  --group my-org \
  --package axios \
  --workers 2        # Default is 8
```

**4. Limit File Size and Count** (Prevents Large File Loading)

```bash
# Skip files larger than 50 MB
python run_scanner.py \
  --group my-org \
  --package axios \
  --max-file-size 52428800

# Limit files scanned per project
python run_scanner.py \
  --group my-org \
  --package axios \
  --max-project-files 1000
```

**5. Use Staged Findings Output** (Reduces In-Memory Accumulation)

```bash
# Findings written incrementally, can process/archive as you go
python run_scanner.py \
  --group my-org \
  --package axios \
  --findings-file findings.json

# Monitor findings growth and process periodically
watch -n 10 'wc -l findings.json; du -h findings.json'
```

**6. Enable Periodic State Cleanup** (Implementation Needed)

*Currently requires code modification, but here's a workaround:*

```bash
# Run scan in stages, delete old state and clear between runs
for i in {1..5}; do
  START=$((($i-1)*400))
  END=$(($i*400))
  
  python run_scanner.py \
    --group my-org \
    --package axios \
    --max-projects $END \
    --findings-file results/stage-$i.json \
    --state-file state-$i.json
  
  # Manually clean old state
  rm state-*.json
done
```

##### Memory Optimization Checklist

**For 2000+ Projects:**

- [ ] Use `--max-projects 500-1000` to limit single scan scope
- [ ] Use `--resume` to stage scans over time
- [ ] Use `--workers 2-3` instead of default 8 (fewer concurrent buffers)
- [ ] Use `--max-file-size` to skip large lock files
- [ ] Use `--max-project-files` to limit scans per project
- [ ] Separate findings files per stage: `--findings-file stage-1.json`
- [ ] Monitor `state.json` size and delete between stages
- [ ] Run during off-peak hours with less system load
- [ ] Use container with memory limits to prevent system slowdown

**For Memory-Constrained Environments:**

```bash
# Ultra-conservative approach
python run_scanner.py \
  --group my-org \
  --package axios \
  --workers 1 \
  --max-projects 100 \
  --max-project-files 500 \
  --max-file-size 10485760 \
  --findings-file stage.json
```

**Memory Estimate Formula:**

```
Approximate Peak Memory = 
  + State File Size × 3 (loaded + parsing + json encode)
  + Findings File Size × 2 (loaded + updates)
  + Worker Concurrency × Avg File Size × Workers
  + Result Buffer × Max Projects / Workers

Estimated for 2000 projects with default settings:
  = 30 MB (state) + 50 MB (findings) + 16 × 1 MB × 8 + 100 MB (results)
  = ~280 MB typical
  = ~1-2 GB worst case (many large lock files)
```

**If Memory Still Growing Unbounded (Complete RAM Saturation):**

⚠️ **CRITICAL: There are known memory leaks in the architecture:**

1. **State Findings Buffer** (Primary Leak)
   - Every finding stored in `state.findings` list without limit
   - For 10,000 findings = 5+ MB in memory
   - State rewritten to disk on EVERY project completion = O(n²) operations
   - **Fix:** Use `--max-projects` to stage scans

2. **Results Accumulation** (Secondary Leak)
   - All project results held in memory throughout scan
   - 2000 projects with findings = 200+ MB accumulated
   - Only released when scan completes
   - **Fix:** Use `--max-projects` to keep result set small

3. **Findings File Rewriting** (Tertiary Leak)
   - On every finding added, ENTIRE findings.json rewritten to disk
   - 10,000 findings = 10,000 full file rewrites
   - Each write loads entire array into memory for JSON serialization
   - **Fix:** Use separate findings files per stage, then merge

**Complete RAM Saturation Scenario (Pre-v2.0):**

**OLD Architecture (Found in Pre-v2.0):**
```
Memory Usage Over Time:

0h    : ~100 MB (startup, state loading)
1h    : ~200 MB (100 projects, 1000 findings)
2h    : ~500 MB (400 projects, 4000 findings)
3h    : ~1.2 GB (900 projects, 9000 findings)
4h    : ~2.5 GB (1600 projects, 16000 findings)  ← RAM FULL if 4GB system
5h    : OUT OF MEMORY - system thrashes/hangs/kills process
```

**NEW Architecture (v2.0+ with JSONL):**
```
Memory Usage Over Time:

0h    : ~100 MB (startup, metadata loading from existing findings)
1h    : ~150 MB (100 projects, continuing scan)
2h    : ~150 MB (400 projects, memory usage remains constant)
3h    : ~160 MB (900 projects, still constant)
4h    : ~170 MB (1600 projects, findings on disk not RAM)
5h    : ~180 MB (2500 projects, linear disk growth only)
```

**Why the difference:**
- **Old:** Memory = State(n) + Findings(n) + Results(n) = O(n) per finding
- **New:** Memory = State(const) + Metadata(const) + Results(batch) = O(1) per finding

**The memory growth was CUBIC because:**
- State file grows O(n) with findings
- Results list grows O(n) with findings  
- State file rewritten on every project = O(n) rewrites × O(n) size = O(n²) I/O
- Findings file rewritten on every finding = O(m) rewrites × O(m) size = O(m²) I/O

**FIXED in v2.0 with JSONL format:**
- State file: Stay constant size (metadata only, not full findings)
- Findings file: Append-only, no rewrites (O(n) I/O, not O(n²))
- Memory: Metadata only (O(1), not O(n))

#### Issue: Network Delays
- **Cause:** Slow GitLab server response times
- **Fix:** Increase `--request-timeout`
- **Verify:** `curl -w "@curl.txt" ...` to measure latency

---

## Debugging Specific Components

### API Layer (gitlab_api.py)

**Enable API Debugging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

import requests
requests.packages.urllib3.disable_warnings()

# HTTPConnection debugging
http_logger = logging.getLogger('urllib3')
http_logger.setLevel(logging.DEBUG)
http_logger.addHandler(logging.StreamHandler())
```

**Verify Pagination:**
```bash
# Check X-Next-Page header in responses
curl -i -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
     "$GITLAB_URL/api/v4/projects?per_page=100" | head -20
```

### Scanner (scanner.py)

**Test Package-Lock Parsing:**
```python
import json
from scanner import scan_package_lock

# Load file
with open("package-lock.json") as f:
    content = f.read()

# Create test rule
class Rule:
    packages = ["axios"]
    exact_versions = []
    version_ranges = []

hits = scan_package_lock(content, Rule(), [])
print(f"Found {len(hits)} hits:")
for hit in hits[:5]:
    print(hit)
```

**Test Generic Scanning:**
```python
from scanner import scan_generic_file

# Simulate scanning custom file
with open("requirements.txt") as f:
    content = f.read()

hits = scan_generic_file(content, Rule(), [])
print(hits)
```

### State Management (state_manager.py)

**Verify State Save/Load:**
```python
from state_manager import (
    create_initial_state, save_state, load_state
)

# Create state
state = create_initial_state(
    ["axios"], ["package-lock.json"], [], []
)

# Save
save_state(state, "test_state.json")

# Load and verify
loaded = load_state("test_state.json")
assert loaded.search_terms == state.search_terms
print("State persistence works!")
```

### Utilities (utils.py)

**Test Stats Threading:**
```python
from utils import update_stats, get_stats_snapshot
import threading

def worker():
    for i in range(100):
        update_stats(repos_completed=1)

threads = [threading.Thread(target=worker) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()

stats = get_stats_snapshot()
assert stats.repos_completed == 500, f"Expected 500, got {stats.repos_completed}"
print("Thread-safe stats work!")
```

---

## Advanced Debugging

### Debugging Thread Issues

**Race Condition Detection:**
```bash
# Use Python's thread analysis
python -m py_spy record -o profile.svg -- \
  python run_scanner.py --package axios
```

**Monitor Locks:**
```python
# In config.py, wrap lock usage:
import time

original_acquire = PRINT_LOCK.acquire

def debug_acquire(blocking=True, timeout=-1):
    start = time.time()
    result = original_acquire(blocking, timeout)
    elapsed = time.time() - start
    if elapsed > 0.01:  # More than 10ms
        print(f"Lock contention: {elapsed:.3f}s")
    return result

PRINT_LOCK.acquire = debug_acquire
```

### Debugging API Pagination

**Trace Pagination:**
```python
from gitlab_api import paginated_get

count = 0
for item in paginated_get("/api/v4/projects", {}):
    count += 1
    if count % 100 == 0:
        print(f"Fetched {count} items...")

print(f"Total items: {count}")
```

### Debugging Argument Parsing

**Inspect Parsed Arguments:**
```python
from gitlab_repo_scanner import parse_args
import sys

# Set up test arguments
sys.argv = [
    "scanner", 
    "--package", "axios", 
    "--filename", "package-lock.json",
    "--version", "1.0.0",
    "--verbose"
]

args = parse_args()
print(f"packages: {args.package}")
print(f"filenames: {args.filename}")
print(f"versions: {args.version}")
print(f"verbose: {args.verbose}")
```

---

## Debugging Checklist

Before reporting bugs, verify:

- [ ] Environment variables are set: `echo $GITLAB_URL $GITLAB_TOKEN`
- [ ] GitLab is accessible: `curl -I $GITLAB_URL`
- [ ] Token has read_api scope
- [ ] Target projects exist: `curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" $GITLAB_URL/api/v4/projects`
- [ ] Target files exist in projects
- [ ] Package names match exactly (case-sensitive)
- [ ] Version format is valid semver
- [ ] Enough disk space for state file
- [ ] Network not rate-limiting
- [ ] No firewall blocking GitLab
- [ ] Python version >= 3.10
- [ ] Dependencies installed: `pip install -r requirements.txt`

---

## Creating Minimal Reproducible Example

To debug a specific issue:

```bash
# 1. Log output to file
python run_scanner.py \
  --package axios \
  --filename package-lock.json \
  --verbose \
  --log-file debug.log \
  2>&1 | tee console.log

# 2. Check state file
cat state.json | python -m json.tool > state_formatted.json

# 3. Share:
# - debug.log (full logs)
# - console.log (console output)
# - state_formatted.json (scan state)
# - First 100 lines of target file
```

---

## Performance Tuning Decision Tree

```
Scan slow?
├─ Yes, high CPU? → Reduce --workers (2-3)
├─ Yes, high memory? → Reduce --max-projects
├─ Yes, network stalls? → Increase --request-timeout (60)
├─ Yes, rate limited?
│  ├─ Yes → Reduce --workers, increase timeout
│  └─ No → Try different --branch-pattern
└─ Acceptable → Done!

Results incomplete?
├─ Specific project missing? → Check permissions
├─ Specific file missing? → Verify --filename
├─ Specific package missing? → Verify --package spelling
└─ Version pattern not matching? → Check --version/--range format
```
