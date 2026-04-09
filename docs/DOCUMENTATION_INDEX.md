# Documentation Index

Complete guide to all project documentation files and how to use them.

## 📚 Documentation Files Overview

```
Documentation Files:
├── README.md                      # Start here! Basic usage, testing guide
├── LLMS_GUIDE.md                 # Architecture for AI/LLM interpretation
├── MODULE_REFERENCE.md           # Complete function reference with signatures
├── DEBUGGING_GUIDE.md            # Troubleshooting and performance debugging
├── ARCHITECTURE_DECISIONS.md     # Design decisions, trade-offs, rationale
├── TEST_RESULTS.md               # Test documentation and results
└── DOCUMENTATION_INDEX.md        # This file

Code Files (in /src/):
├── run_scanner.py                # Entry point (dynamically loads main module)
├── gitlab_repo_scanner.py        # Orchestration and CLI
├── gitlab_api.py                 # GitLab REST API interaction
├── scanner.py                    # File parsing (structured and generic)
├── state_manager.py              # Scan state persistence
├── utils.py                      # Shared utilities and logging
├── config.py                     # Configuration and constants
└── __init__.py                   # Package marker

Test Files (in /tests/):
├── test_options.py               # CLI argument parsing tests (23 tests)
├── test_functionality.py         # Business logic tests (15 tests)
└── test_lock_file_parsers.py     # Lock file format parser tests (25 tests)
```

## 🎯 Quick Start by Use Case

### "I want to RUN the scanner"
1. Read: README.md - Installation & Usage section
2. Set environment variables: `GITLAB_URL`, `GITLAB_TOKEN`
3. Run: `python run_scanner.py --package axios --filename package-lock.json`

### "I want to UNDERSTAND the code"
1. Read: LLMS_GUIDE.md - Architecture section
2. Read: ARCHITECTURE_DECISIONS.md - Key decisions
3. Browse: Code files with inline comments
4. Reference: MODULE_REFERENCE.md - Function details

### "I want to DEBUG an issue"
1. Read: DEBUGGING_GUIDE.md
2. Check: Common Issues & Solutions
3. Enable verbose logging: `--verbose` flag
4. Reference: LOG FILES section for interpretation

### "I want to OPTIMIZE performance"
1. Read: DEBUGGING_GUIDE.md - Performance Debugging
2. Read: ARCHITECTURE_DECISIONS.md - Section 16: Findings Storage Format
3. Profile: Use built-in timing or cProfile
4. Tune: Adjust `--workers`, `--request-timeout`, `--max-projects`
5. Check: Expected memory usage ~150-200MB even for 2000+ projects

### "I want to SCALE to 2000+ repositories"
1. Read: ARCHITECTURE_DECISIONS.md - Section 16: Findings Storage Format
2. Read: DEBUGGING_GUIDE.md - Memory Architecture section
3. Use: `python run_scanner.py --group my-org --package axios`
4. Expect: Peak RAM ~200-300MB for 100,000 findings
5. Verify: Findings stored on disk in JSONL format (~50-80MB for dense findings)

### "I want to TEST the scanner"
1. Read: README.md#testing - Testing section
2. Read: TEST_RESULTS.md - Test documentation
3. Run: `python tests/test_options.py` and `python tests/test_functionality.py`
4. Add: New tests for new features

---

## 🚀 Recent Improvements (v2.0+)

### Memory Optimization: JSONL Findings Format
**What Changed:** Findings now use JSONL (JSON Lines) append-only format instead of JSON arrays

**Benefits:**
- ✅ **5-10x memory reduction:** Peak RAM 100-200MB instead of 2-5GB for large scans
- ✅ **Constant memory usage:** Memory doesn't grow with finding count (O(1) instead of O(n))
- ✅ **Faster I/O:** Append-only writes (O(n)) instead of full rewrites (O(n²))
- ✅ **Large scans enabled:** 2000+ repositories now scannable without RAM exhaustion
- ✅ **Streaming support:** Process findings line-by-line without loading entire file

**Files Affected:**
- `findings.json` - Now JSONL format (one finding per line)
- `findings_manager.py` - Append-only, metadata-only buffering
- `state_manager.py` - Simplified, no findings list storage

**Documentation:**
- README.md - Section "Findings Storage Format" explains JSONL
- ARCHITECTURE_DECISIONS.md - Section 16 has full design decision
- DEBUGGING_GUIDE.md - Updated memory estimates and monitoring

---

## 📖 File Descriptions

### README.md
**Purpose:** Primary documentation for users

**Sections:**
- Project overview
- Installation and setup
- Usage and CLI options
- Example commands
- Testing guide for reproducibility
- Troubleshooting basics

**Read When:** First time learning about project, setting up for first run

---

### LLMS_GUIDE.md
**Purpose:** Complete guide for AI/LLM systems analyzing the code

**Sections:**
- Quick overview
- Architecture & system design
- Module dependencies with diagrams
- Data flow for parallel scanning
- Key data structures
- Threading & concurrency safety
- Performance characteristics
- Key functions to understand
- Extension points
- Performance tuning
- Testing guide for LLMs

**Read When:** 
- You're an LLM analyzing this code
- You want comprehensive architectural understanding
- You're planning major modifications

---

### MODULE_REFERENCE.md
**Purpose:** Complete reference for all modules and functions

**Contents:**
- All 7 modules covered
- Every function with:
  - Purpose
  - Parameters and types
  - Return values
  - Implementation details
  - Examples where applicable
- Data structures documented
- Quick lookup sections
- "Function lookup by purpose" guide

**Read When:**
- You need to understand a specific function
- You're writing code that calls another module
- You're creating new features in a module

---

### DEBUGGING_GUIDE.md
**Purpose:** Comprehensive troubleshooting resource

**Sections:**
- Quick diagnostics (verbosity, logs, state inspection)
- Common issues & solutions:
  - Authentication failures
  - Rate limiting
  - No findings found
  - Crashes and recovery
  - File size issues
  - Version parsing errors
  - Duplicate results
- Performance debugging
- Component-specific debugging
- Advanced debugging techniques
- Debugging checklist
- Performance tuning decision tree

**Read When:**
- Something isn't working
- Performance seems slow
- You're seeing unexpected results
- You need to understand error handling

---

### ARCHITECTURE_DECISIONS.md
**Purpose:** Explain WHY design decisions were made

**Sections for Each Major Decision:**
- The decision itself
- Why it was made
- Trade-offs (alternatives considered)
- Implementation details
- Limitations
- When to change approach

**Topics Covered:**
1. Threading & parallelization
2. State persistence
3. Structured vs generic file parsing
4. Multi-format lock file support (11 formats: npm, yarn, poetry, pipenv, go, rust, ruby, php, java, dart)
5. Version matching strategy
6. API rate limiting
7. Error handling
8. Logging architecture
9. Configuration management
10. Progress tracking
11. Argument validation
12. Dependency choices
13. Project structure
14. Testing strategy
15. Concurrency safety
16. Performance vs maintainability

**Read When:**
- You disagree with a design decision
- You want to implement a feature differently
- You need to understand trade-offs
- You're extending the project significantly

---

### TEST_RESULTS.md
**Purpose:** Document test coverage and results

**Contents:**
- Test suite organization
- All 35 tests documented
- Test categories:
  - Argument parsing (23 tests)
  - State management (6 tests)
  - Scanner functions (3 tests)
  - Utility functions (3 tests)
- How to run tests
- Expected results
- Test results snapshot

**Read When:**
- Running tests for first time
- Adding new tests
- Verifying test coverage
- Understanding test structure

---

## 👤 Documentation by Audience

### End User (Running the scanner)
**Essential:**
1. README.md - Usage guide
2. DEBUGGING_GUIDE.md - Troubleshooting

**Optional:**
- ARCHITECTURE_DECISIONS.md - Performance tuning section

### Developer (Modifying code)
**Essential:**
1. README.md - Setup
2. MODULE_REFERENCE.md - Function details
3. ARCHITECTURE_DECISIONS.md - Extensibility points

**Important:**
- LLMS_GUIDE.md - System understanding
- DEBUGGING_GUIDE.md - Testing changes

**Reference:**
- Inline code comments
- TEST_RESULTS.md - Test examples

### AI/LLM System (Analyzing code)
**Essential:**
1. LLMS_GUIDE.md - Architecture overview
2. MODULE_REFERENCE.md - Function reference

**Important:**
- ARCHITECTURE_DECISIONS.md - Design rationale
- Inline code comments

**Reference:**
- DEBUGGING_GUIDE.md - Error patterns
- TEST_RESULTS.md - Expected behavior

### DevOps/SRE (Running in production)
**Essential:**
1. README.md - Usage and installation
2. DEBUGGING_GUIDE.md - Troubleshooting
3. ARCHITECTURE_DECISIONS.md - Performance tuning

**Important:**
- LLMS_GUIDE.md - Threading and resource usage
- MODULE_REFERENCE.md - API rate limiting

---

## 🔍 Finding Specific Information

### "How do I...?"

#### ...set up the scanner?
→ README.md

#### ...understand the architecture?
→ LLMS_GUIDE.md#architecture--system-design

#### ...debug a specific error?
→ DEBUGGING_GUIDE.md#common-issues--solutions

#### ...add a new feature?
→ ARCHITECTURE_DECISIONS.md#extensibility-points

#### ...understand how version matching works?
→ MODULE_REFERENCE.md or code comments in scanner.py

#### ...optimize performance?
→ DEBUGGING_GUIDE.md#performance-debugging

#### ...run tests?
→ README.md#testing or TEST_RESULTS.md

#### ...understand concurrency?
→ LLMS_GUIDE.md#threading--concurrency-safety

#### ...find a specific function?
→ MODULE_REFERENCE.md#quick-function-lookup-by-purpose

#### ...understand a design decision?
→ ARCHITECTURE_DECISIONS.md

---

## 📊 Documentation Coverage

| Topic | Covered In |
|-------|-----------|
| Installation | README.md |
| Basic usage | README.md |
| All CLI options | README.md |
| Architecture | LLMS_GUIDE.md, code comments |
| Every function | MODULE_REFERENCE.md, code comments |
| Design decisions | ARCHITECTURE_DECISIONS.md |
| Troubleshooting | DEBUGGING_GUIDE.md |
| Testing | README.md, TEST_RESULTS.md |
| Performance | DEBUGGING_GUIDE.md, ARCHITECTURE_DECISIONS.md |
| Concurrency | LLMS_GUIDE.md, ARCHITECTURE_DECISIONS.md, code comments |
| Error handling | LLMS_GUIDE.md, ARCHITECTURE_DECISIONS.md, code comments |
| Extensibility | ARCHITECTURE_DECISIONS.md |
| Lessons learned | ARCHITECTURE_DECISIONS.md |

---

## ✅ Navigation Tips

- Start with README.md for basic usage
- Use DOCUMENTATION_INDEX.md (this file) to navigate to specific topics
- Check inline code comments for implementation details
- Refer to ARCHITECTURE_DECISIONS.md when making design choices
- Use DEBUGGING_GUIDE.md for troubleshooting issues
- Run tests to verify changes
