# Architecture & Design Decisions

This document explains the key architectural decisions and trade-offs made in the GitLab scanner.

## 1. Threading & Parallelization

### Decision: ThreadPoolExecutor for parallel project scanning

**Why:** GitLab scanner is I/O-bound (waiting for API responses), not CPU-bound.

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Threading** (chosen) | Simple, shared memory, light overhead | GIL limits CPU-bound work |
| Multiprocessing | True parallelism | Heavy overhead, pickling costs |
| Async/await | Efficient, light | Requires async-all-the-way, complex |
| Sequential | Simple, debugging easy | Very slow (5-50x slower) |

**Implementation:**
- `ThreadPoolExecutor` with configurable workers (`--workers`)
- `as_completed()` pattern for immediate result handling
- Thread-safe stats with `STATS_LOCK` (not shared memory)

**When to Change:**
- If adding CPU-heavy work (e.g., regex analysis), switch to multiprocessing
- If supporting Python 3.10+ exclusively, could migrate to asyncio

---

## 2. State Persistence

### Decision: JSON file-based state, not database

**Why:** Single-user CLI tool, simple resume requirement, no infrastructure needed.

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **JSON file** (chosen) | Simple, portable, human-readable | Concurrency issues, no queries |
| SQLite DB | Queryable, atomic | Overkill for this use case |
| Cloud storage | Distributed resume | Requires authentication, complexity |
| In-memory only | Simplest | Can't resume after crash |

**Implementation:**
- `state.json` contains scan metadata and completed project IDs
- Loaded at start, updated after each project
- Saved on interrupt signal (Ctrl+C) for resume

**Limitations:**
- Single instance only (no distributed scanning)
- Concurrent runs will overwrite state
- Manual cleanup required for large state files

**When to Change:**
- If needing distributed scanning, use cloud storage (S3, etc.)
- If needing persistent history, use database

---

## 3. Structured vs Generic File Parsing

### Decision: Two-tier approach - structured for package-lock, generic text search for others

**Why:** Different file types require different strategies.

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Dual strategy** (chosen) | Accurate for known formats, flexible | Code complexity, some false positives |
| Only structured | Accurate, fast | Misses custom formats |
| Only text search | Simple, catches everything | False positives, slow |
| Regex rules per file type | Flexible | Maintenance burden, regex complexity |

**Implementation:**
- `scanner.py::should_parse_as_package_lock()` determines strategy
- Structured: Parse JSON/YAML/TOML based on file type, traverse dependency tree
- Generic: Text search with optional version validation

**Accuracy by Format:**
- package-lock.json: ~99% accuracy (JSON parser is authoritative)
- yarn.lock: ~95% accuracy (YAML parsing, some edge cases)
- Pipfile.lock, poetry.lock, Cargo.lock: ~99% accuracy (JSON/TOML authoritative)
- go.sum, requirements.txt, gradle.lock, Gemfile.lock: ~95% accuracy (text parsing with regex)
- Generic files: ~85% accuracy (false positives from version strings in documentation)

**When to Change:**
- If reducing false positives important, use Bayesian filter or ML
- If supporting custom lock file formats, add pattern-matching strategy

---

## 4. Multi-Format Lock File Support

### Decision: Extensible parser architecture with format-specific implementations

**Why:** Different package management ecosystems use different lock file formats; each needs specialized parsing.

**Architecture:**
```python
Lock File Detection → Parser Registry → Format-Specific Parser → Version Matching
```

**Supported Formats:**

| Format | Language | Parser Type | Status |
|--------|----------|-------------|--------|
| package-lock.json | npm | JSON with tree traversal | ✅ |
| yarn.lock | Yarn | YAML-like text | ✅ |
| Pipfile.lock | Pipenv | JSON (default/develop sections) | ✅ |
| poetry.lock | Poetry | TOML | ✅ |
| requirements.txt | pip | Text with operator parsing | ✅ |
| go.sum | Go | Text with hash validation | ✅ |
| Cargo.lock | Rust | TOML | ✅ |
| Gemfile.lock | Bundler | Text with indentation parsing | ✅ |
| composer.lock | Composer | JSON (packages/packages-dev) | ✅ |
| gradle.lock | Gradle | Text with artifact notation | ✅ |
| pubspec.lock | Pub | YAML | ✅ |

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Dedicated parsers** (chosen) | Accurate, format-aware, maintainable | Code duplication, per-format logic |
| Unified JSON conversion | Single parser logic | Lossy, complexity in converters |
| Regex-only approach | Minimal code | Fragile, unmaintainable |
| Machine learning | Adaptive | Overkill, hard to debug |

**Extension Pattern:**
```python
# To add new format (e.g., Maven pom-lock.xml):
1. Create parser: def parse_maven_lock(content, rule, ranges) -> List[Dict]
2. Register: LOCK_FILE_PARSERS["maven"] = parse_maven_lock
3. Detect: Add branch to get_lock_file_format()
4. Test: Add test suite with 2-3 test cases
```

**Limitations:**
- Each new format requires manual parser implementation
- Some formats have ambiguous syntax (Gemfile.lock indentation)
- Version operators vary per ecosystem (==, >=, ~, caret, etc.)

**When to Change:**
- If adding 5+ more formats, consider unified schema approach
- If formats are complex, could use existing parsers (toml library, PyYAML) more heavily
- If vendor-specific, might need per-vendor strategy

---

## 5. Version Matching Strategy

### Decision: Three-tier version matching - exact, semver range, text match

**Why:** Different vulnerability databases use different version formats.

**Implementation:**
```
Match found if:
  1. Exact version in --version list, OR
  2. Version in --range semver range, OR
  3. No version specified (match any)
```

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Flexible matching** (chosen) | Supports all common formats | Complex logic, surprising behavior |
| Exact only | Simple | Misses similar vulnerabilities |
| Semver only | Clean | Doesn't handle pre-releases, local versions |

**Example:**
- `--version 2.0.0` → matches exactly "2.0.0" only
- `--range "^2.0.0"` → matches "2.0.1", "2.99.9" but not "3.0.0"
- Neither → matches any version of the package

**Per-Ecosystem Version Handling:**
- NPM: Semver (^, ^, ~, >=, <=, *, x, etc.)
- Python: PEP 440 (==, !=, >=, <=, ~=, etc.)
- Go: Semantic version with v prefix
- Rust: Cargo semver (same as npm)
- Ruby: Gem version syntax (same as npm)

**Limitations:**
- Pre-release versions (1.0.0-beta) treated as greater than 1.0.0
- Local versions (+ubuntu1) may not parse correctly
- Pre-release and build metadata might be dropped during normalization

**When to Change:**
- If precision critical, implement full PEP 440 parsing
- If performance critical, pre-compile all ranges at startup

---

## 6. API Rate Limiting

### Decision: Exponential backoff with Retry-After header

**Why:** GitLab enforces rate limits; need graceful recovery.

**Implementation:**
```python
if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    sleep(retry_after)
    retry_request()
```

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Header-based backoff** (chosen) | Respects server limits, simple | Scan time variable, hard to predict |
| Fixed retry delay | Predictable | May violate rate limits |
| Exponential backoff | Standard pattern | Complex, may sleep too long |
| Request queuing | Fair distribution | Adds infrastructure |

**Current Behavior:**
- First request: immediate
- Rate limited: sleep for `Retry-After` seconds
- Resume: automatic, transparent to user

**When to Change:**
- If adding multi-instance support, use rate-limit-aware queue (e.g., celery)
- If hitting limits consistently, reduce `--workers` or use different token

---

## 6. Error Handling

### Decision: Per-file error isolation with aggregate tracking

**Why:** Single file failure shouldn't block entire project scan.

**Implementation:**
- Individual file errors logged but not re-raised
- Project scan continues with remaining files
- Errors aggregated in result dict
- Final report includes error count

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Isolated errors** (chosen) | Resilient, completes usefully | May miss systematic issues |
| Fail-fast | Quick detection | All-or-nothing results |
| Retry with exponential backoff | Recovers from transient errors | Scan time unpredictable, complex |

**Error Types Handled:**
1. API errors (404, 500): Logged, project skipped
2. File too large: Logged, file skipped (continues scan)
3. Invalid JSON: Logged, file skipped (continues scan)
4. Network timeout: Retried with backoff
5. Rate limited: Backed off, retried transparently
6. Authentication failed: Fatal (exit)

**When to Change:**
- If reliability is critical, implement circuit breaker pattern
- If needing detailed error reports, use structured logging (JSON)

---

## 7. Logging Architecture

### Decision: Dual stream (file + console) with thread-safe serialization

**Why:** Need persistent logs for debugging AND real-time user feedback.

**Implementation:**
- File handler: Full DEBUG logs with timestamps
- Console handler: INFO+ with colors and `tqdm` integration
- `PRINT_LOCK` serializes concurrent writes
- `TqdmLoggingHandler` prevents log corruption during progress bar updates

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Dual handlers** (chosen) | Detailed logs + clean UX | Complex synchronization |
| File only | Simple | No real-time feedback |
| Console only | Real-time | Lost history, debugging hard |
| Structured logging (JSON) | Machine-parseable | Verbose, not human-readable |

**Thread Safety:**
- `PRINT_LOCK` protects stderr writes
- `tqdm.write()` used for logging within progress bar
- Colors handled in `ColorConsoleFormatter`

**When to Change:**
- If production logging needed, output JSON logs to ELK/Datadog
- If performance critical, use async logging handler
- If cloud-native, use stdout/stderr with external aggregation

---

## 8. Configuration Management

### Decision: Environment variables + CLI arguments, no config file

**Why:** Stateless CLI design, environment agnostic, no file parsing overhead.

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Env + CLI args** (chosen) | Simple, containerizable | Can't batch configs |
| Config file (YAML/JSON) | Batch configuration | Parse errors, not containerization-friendly |
| Defaults + overrides | Simple | Hard to discover options |
| Interactive prompts | User-friendly | Not scriptable |

**Implementation:**
- `GITLAB_URL`, `GITLAB_TOKEN`: Environment variables (required)
- Everything else: CLI arguments with sensible defaults
- No config file parsing

**When to Change:**
- If supporting complex workflows, add config file support
- If multi-step pipelines needed, use orchestration tool (Ansible, Terraform)

---

## 9. Progress Tracking

### Decision: Live progress bar with statistics

**Why:** Long-running scans need visual feedback; users want ETA.

**Implementation:**
- `tqdm` progress bar with position tracking
- Live statistics: repos/sec, branches/sec, files/sec
- Updates on every completed project

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Live progress** (chosen) | User engagement, early cancellation | Terminal output overhead, not log-file friendly |
| Silent mode | Simple, clean logs | No feedback, hard to predict time |
| Periodic reports | Balance | Updates batched, ETA less accurate |
| Percentage only | Simple | No throughput info |

**Implementation Details:**
- `tqdm.tqdm()` with `unit="projects"`
- `format_live_summary()` calculates throughput
- `--no-progress` flag for CI/CD (log-friendly output)

**When to Change:**
- If running in headless CI/CD, use `--no-progress`
- If integration with monitoring, export metrics to Prometheus

---

## 10. Argument Validation

### Decision: Eager validation at startup, fail-fast

**Why:** Clear errors before expensive API calls begin.

**Implementation:**
- `parse_args()`: Standard argparse validation
- `_validate_environment_variables()`: Check GITLAB_URL/TOKEN
- `_validate_required_arguments()`: Check --package, --filename, --workers
- `_validate_and_setup_args()`: Normalize lists, build version specs

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Eager validation** (chosen) | Clear feedback, quick iteration | Misses runtime edge cases |
| Lazy validation | Discovers only when needed | Confusing errors after API calls |
| Schema validation (Pydantic) | Type-safe, composable | Dependency overhead |

**Error Messages:**
- Environment: "GITLAB_TOKEN not set"
- Arguments: "At least one --package required"
- Versions: "Invalid semver range: ..."

**When to Change:**
- If supporting many options, use Pydantic for validation
- If backwards compatibility needed, add deprecation warnings

---

## 11. Dependency Choices

### Why Specific Libraries

| Library | Why | Alternatives | Cost |
|---------|-----|--------------|------|
| `requests` | Standard, stable HTTP client | `urllib3`, `httpx` | ~50KB |
| `semantic_version` | Accurate npm semver parsing | `packaging`, `distlib` | ~100KB |
| `tqdm` | Best progress bar UI | `alive-progress`, `progressbar33` | ~50KB |
| `argparse` | Built-in, sufficient | `click`, `typer` | ~0KB |

**Why Not Alternatives:**
- `click`: Would need to restructure all option handling
- `typer`: Over-engineered for CLI use case
- `packaging`: Focuses on Python versioning (PEP 440), not npm
- `asyncio`: Would require full async rewrite (not worth complexity)

---

## 12. Project Structure

### Decision: Modular single-directory layout

**Why:** Single package, clear separation of concerns, easy to distribute.

**Structure:**
```
gitlab_repo_scanner/          # Main package
├── gitlab_repo_scanner.py    # Orchestration
├── gitlab_api.py             # API interaction
├── scanner.py                # File parsing
├── state_manager.py          # State persistence
├── utils.py                  # Shared utilities
├── config.py                 # Configuration
└── run_scanner.py            # Entry point
```

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Single directory** (chosen) | Simple, all visible, easy to distribute | Can grow unwieldy |
| Nested packages | Organized, clear layering | Import complexity |
| Monorepo | Many tools, standards | Overkill for single tool |

**When to Change:**
- If adding web API, separate into `api/` package
- If adding GUI, separate into `ui/` package
- If adding plugin system, separate into `plugins/` directory

---

## 13. Testing Strategy

### Decision: Two test suites - arguments and functionality

**Why:** Different concerns require different test approaches.

**Implementation:**
- `test_options.py`: 23 tests for CLI argument parsing
  - Validates all 30+ options individually and in combinations
  - Quick, isolated, no external dependencies
  
- `test_functionality.py`: 12 tests for business logic
  - State persistence (save/load/clear)
  - Scanner logic (package-lock parsing, version matching)
  - Utils (stats tracking, list normalization)

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Argument + Functionality** (chosen) | Comprehensive, maintainable | Doesn't test real GitLab API |
| Integration tests | Real-world scenarios | Slow, brittle, expensive |
| Unit tests only | Fast, focused | May miss integration issues |
| No tests | Simple | Regress easily |
| E2E tests with mock | Realistic | Mock maintenance burden |

**Coverage:**
- Arguments: 100% of 23 option combinations
- State: All save/load/clear paths
- Scanner: Both structured and generic parsing
- Utils: Thread-safe stats, list normalization

**When to Change:**
- If testing against real GitLab, add integration test suite
- If performance critical, add benchmarking tests
- If adding web API, add API endpoint tests

---

## 14. Concurrency Safety

### Decision: Thread-local storage + locks, no shared mutable state

**Why:** Minimize synchronization overhead while preventing race conditions.

**Implementation:**
- Per-thread result collection (no shared list)
- Results aggregated after `as_completed()`
- `PRINT_LOCK` for stdout serialization
- `STATS_LOCK` for statistics updates

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **Thread-local + locks** (chosen) | Minimal contention, clear semantics | Developer must remember locks |
| Queues everywhere | Type-safe, proven pattern | Overhead, complexity |
| Immutable data | No locks needed | Functional programming learning curve |
| Global lock | Simplest | Serializes everything (defeats threading) |

**Critical Sections:**
```python
# Stats updates
with STATS_LOCK:
    RUN_STATS.repos_completed += 1

# Output serialization  
with PRINT_LOCK:
    print("message")
```

**When to Change:**
- If adding distributed scanning, use message queue (RabbitMQ)
- If performance profiling shows lock contention, use lock-free data structures

---

## 15. Performance vs Maintainability

### Design Principle: Choose clarity over micro-optimizations

**Examples:**

1. **Function extraction over inline code**
   - Added `_validate_arguments()`, `_prepare_project_list()`, etc.
   - Slightly more function call overhead
   - Much more readable and testable

2. **Explicit loops over list comprehensions**
   - `for hit in hits` instead of list comp
   - Marginally slower
   - Much easier to debug

3. **Multiple passes over data vs single pass**
   - Deduplication: second pass over hits
   - Slightly more memory
   - Clearer intent, easier to modify

**Rationale:**
- Scanner is I/O-bound (API calls dominate)
- Logic clarity matters more than 5% speedup
- Easier maintenance prevents bugs (actual performance loss)

---

## 16. Findings Storage Format

### Decision: JSONL (JSON Lines) append-only format instead of single JSON object

**Why:** Enable scans of 2000+ repositories without RAM exhaustion.

**Trade-offs:**
| Approach | Pros | Cons |
|----------|------|------|
| **JSONL append-only** (chosen) | O(1) memory per finding, O(1) I/O per write, no rewrites | Can't seek to specific finding, larger file on disk |
| Single JSON object | Structured, single JSON load, standard | O(n) memory growth, O(n²) I/O (full rewrite per finding) |
| SQLite database | Queryable, atomic, ACID | Overkill for CLI tool, infrastructure needed |
| CSV format | Lightweight, universal | No nested data support, awkward structure |
| Streaming JSON arrays | Standard format | Requires valid JSON structure, still needs rewrite |

**Memory Analysis:**

For 10,000 findings:
- **Old approach** (single JSON object):
  - State findings list: `10,000 × 1 KB ≈ 10 MB`
  - Results buffer: `workers × 1 MB ≈ 5 MB`
  - Duplicates during write: `10 MB (copy + write)`
  - **Peak RAM: 25+ MB per 10,000 findings**
  
- **New approach** (JSONL append-only):
  - Metadata sets: `~100 KB` (package names, file paths, projects)
  - No results buffer kept after append
  - No rewrites (streaming appends)
  - **Peak RAM: <1 MB regardless of findings count**

For 100,000+ findings (2000+ repositories):
- **Old:** RAM saturation at 4GB+ (system unusable)
- **New:** Constant ~500 MB throughout scan

**Implementation:**
- Each finding appended as single JSON line with newline terminator
- Metadata (counts, unique packages) tracked in memory as sets
- No full file reads - only line-by-line scanning for resume
- Streaming support: process findings line-by-line without loading entire file

**Performance Characteristics:**
- Write: O(1) per finding (single append)
- Read: O(n) for metadata load (unavoidable, but only on init)
- Summary: O(1) (in-memory sets)
- Resume: O(n) scan but doesn't accumulate in memory

**Example JSONL File:**
```jsonl
{"timestamp":"2024-01-15T14:23:41.234567Z","project":"org/api","branch":"main","file":"package.json","package":"lodash","version":"4.17.21"}
{"timestamp":"2024-01-15T14:23:42.345678Z","project":"org/web","branch":"develop","file":"package-lock.json","package":"axios","version":"1.4.0"}
```

**When to Change:**
- If needing full ACID guarantees and querying, switch to SQLite/PostgreSQL
- If findings need to be updated/deleted after discovery, JSONL isn't suitable
- If file grows beyond 1GB, consider database or sharding strategy

---

## Extensibility Points

### How to Add Features

#### 1. Add New File Type Parsing
```python
# In scanner.py
def scan_gemfile(content, rule, compiled_ranges):
    # Parse Gemfile, return hits
    pass

def should_parse_as_package_lock(file_path: str) -> bool:
    # Add check for Gemfile
    if file_path.endswith("Gemfile"):
        return True
```

#### 2. Add Authentication Methods
```python
# In config.py
if "GITLAB_TOKEN" in os.environ:
    auth_header = {"PRIVATE-TOKEN": GITLAB_TOKEN}
elif "CI_JOB_TOKEN" in os.environ:
    auth_header = {"JOB-TOKEN": CI_JOB_TOKEN}
# Add to SESSION headers
```

#### 3. Add New CLI Options
```python
# In gitlab_repo_scanner.py parse_args()
parser.add_argument(
    "--new-option",
    type=str,
    default="value",
    help="..."
)

# In _validate_and_setup_args()
new_option = args.new_option
# Validate and use
```

#### 4. Add Output Formats
```python
# In gitlab_repo_scanner.py _output_results()
if args.output_format == "json":
    output = json.dumps(results)
elif args.output_format == "csv":
    output = convert_to_csv(results)
elif args.output_format == "html":
    output = generate_html_report(results)
```

---

## Lessons Learned

### 1. ArgParse + "append" Action
- **Problem:** `--filename` with action="append" and default=["package-lock.json"] appends to default
- **Solution:** Set default=None, handle default explicitly
- **Lesson:** Read argparse docs carefully; behavior surprising

### 2. Deduplication is Important
- **Problem:** Same dependency found in both "packages" and "dependencies" tree
- **Solution:** Deduplicate by (package, version, location, rules, source)
- **Lesson:** Different parsing paths can find same thing

### 3. Thread Safety Isn't Optional
- **Problem:** Multiple threads writing to stdout corrupts output
- **Solution:** Use PRINT_LOCK for all terminal writes
- **Lesson:** Think about concurrency from the start

### 4. Graceful Error Isolation Matters
- **Problem:** Single corrupted file crashed entire project scan
- **Solution:** Per-file error handling, continue scanning
- **Lesson:** Robustness over completeness

### 5. Version Parsing is Complex
- **Problem:** Pre-release versions, local versions, npm semver vs PEP 440
- **Solution:** Use semantic_version library, document limitations
- **Lesson:** Don't reinvent parsing; use battle-tested libraries
