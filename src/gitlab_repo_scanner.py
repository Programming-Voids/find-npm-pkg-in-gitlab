#!/usr/bin/env python3
"""
Scan GitLab repositories for packages, versions, or arbitrary strings in repository files.

Features:
- Search for multiple package names or search terms
- Match multiple exact versions
- Match multiple npm-style version ranges
- Search any filename, not just package-lock.json
- Structured parsing for package-lock.json
- Generic text search for other file types
- Target all accessible projects, or specific GitLab groups
- Optional subgroup traversal
- Parallel scanning for better performance
- Scan default branch only, all branches, or only branches matching patterns
- File logging
- Progress bar output
- Per-repository and per-branch terminal logging
- Colorized terminal output
- Per-second throughput stats
- Live summary line

Requirements:
  pip install -r requirements.txt

Environment variables:
  GITLAB_URL   e.g. https://gitlab.example.com
  GITLAB_TOKEN personal/group access token with API read access
"""

import argparse
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

from . import config
from .config import GITLAB_TOKEN, GITLAB_URL
from .findings_manager import FindingsManager
from .gitlab_api import (
    get_file_raw,
    list_target_files,
    list_target_projects,
    project_web_url,
    select_branches_for_project,
)
from .scanner import build_specs, scan_file, should_parse_as_package_lock, get_lock_file_format
from .state_manager import (
    ScanState,
    clear_state,
    create_initial_state,
    filter_completed_projects,
    load_state,
    save_state,
    update_state_with_result,
)
from .utils import (
    ANSI_BLUE,
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_MAGENTA,
    ANSI_RED,
    ANSI_YELLOW,
    LOGGER,
    MatchRule,
    fail,
    format_live_summary,
    get_stats_snapshot,
    log_terminal_line,
    normalize_list,
    setup_logging,
    update_stats,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Scan GitLab repository files for package names, versions, or arbitrary strings."
    )

    parser.add_argument(
        "--package",
        action="append",
        dest="packages",
        required=True,
        help="Search term or package name to look for. Repeatable. Example: --package axios --package plain-crypto-js",
    )

    parser.add_argument(
        "--version",
        action="append",
        dest="versions",
        default=[],
        help="Exact installed version to match. Repeatable. Example: --version 1.14.1",
    )

    parser.add_argument(
        "--range",
        action="append",
        dest="ranges",
        default=[],
        help='npm semver range to match. Repeatable. Example: --range ">=1.14.0 <1.14.2"',
    )

    parser.add_argument(
        "--filename",
        action="append",
        dest="filenames",
        default=None,
        help="Filename to search for. Repeatable. Default: package-lock.json",
    )

    parser.add_argument(
        "--project",
        action="append",
        dest="project_filters",
        default=[],
        help="Only scan projects whose path_with_namespace contains this string. Repeatable.",
    )

    parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        default=[],
        help="GitLab group ID or full path to scan. Repeatable. Example: --group my-org/platform",
    )

    parser.add_argument(
        "--include-subgroups",
        action="store_true",
        help="When used with --group, include subgroup projects too.",
    )

    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived GitLab projects.",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of projects to scan in parallel. Default: 8",
    )

    parser.add_argument(
        "--all-branches",
        action="store_true",
        help="Scan all branches instead of only the default branch.",
    )

    parser.add_argument(
        "--branch-pattern",
        action="append",
        dest="branch_patterns",
        default=[],
        help='Only scan branches matching this shell-style pattern. Repeatable. Example: --branch-pattern "release/*"',
    )

    parser.add_argument(
        "--log-file",
        default="scan_gitlab_package_lock.log",
        help="Path to the log file. Default: scan_gitlab_package_lock.log",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the progress bar.",
    )

    parser.add_argument(
        "--max-file-size",
        type=int,
        default=None,
        help="Maximum file size in bytes. Files larger than this are skipped. Default: unlimited",
    )

    parser.add_argument(
        "--max-project-files",
        type=int,
        default=None,
        help="Maximum files to scan per project. Default: unlimited",
    )

    parser.add_argument(
        "--max-projects",
        type=int,
        default=None,
        help="Maximum projects to scan. Default: unlimited",
    )

    parser.add_argument(
        "--request-timeout",
        type=int,
        default=30,
        help="Timeout for GitLab API requests in seconds. Default: 30",
    )

    parser.add_argument(
        "--state-file",
        default="scan_state.json",
        help="Path to the scan state file for pause/resume. Default: scan_state.json",
    )

    parser.add_argument(
        "--findings-file",
        default="findings.json",
        help="Path to the live findings file that updates during scan. Default: findings.json",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previously paused scan from the state file.",
    )

    parser.add_argument(
        "--clear-state",
        action="store_true",
        help="Clear any previous state file before starting scan.",
    )

    return parser.parse_args()


# Global state for signal handling
# These are global to allow the signal handler to access current scan state
# and save progress when Ctrl+C is pressed during a scan
_current_scan_state: Optional[ScanState] = None
_state_file_path: Optional[str] = None


def _handle_interrupt(signum: int, frame: Any) -> None:
    """Handle Ctrl+C to save state before exiting."""
    if _current_scan_state and _state_file_path:
        print("\n")
        log_terminal_line("[INTERRUPTED] Saving scan state before exit...", ANSI_YELLOW)
        save_state(_current_scan_state, _state_file_path)
        log_terminal_line(
            f"[SAVED] Scan state saved to {_state_file_path}. Resume with --resume flag.",
            ANSI_YELLOW
        )
    sys.exit(1)


def _scan_single_file(
    project_id: int,
    file_path: str,
    branch: str,
    rule: MatchRule,
    compiled_ranges: List[Tuple[str, "NpmSpec"]],
    project_name: str,
    project_url: str,
    findings_manager: Optional["FindingsManager"] = None,
    max_file_size: int = None,
) -> Optional[Dict[str, Any]]:
    """Scan a single file and return finding data if matches are found.
    
    The scanning approach depends on the file type:
    - package-lock.json: Parsed as structured JSON for semantic version matching
    - All other files: Generic text search (substring matching)
    """
    try:
        # Fetch the raw file content from GitLab (respects max_file_size limit)
        raw = get_file_raw(project_id, file_path, branch, max_size=max_file_size)
        if raw is None:
            # File was skipped (e.g., too large)
            LOGGER.info("Skipped %s@%s:%s (exceeds max_file_size=%s)", project_id, branch, file_path, max_file_size)
            return None

        # Determine file type/format for findings tracking
        file_type = get_lock_file_format(file_path)

        # Scan file with automatic format detection and routing
        # - Structured parsing for known lock files (package-lock.json, yarn.lock)
        # - Generic text search as fallback for all other files
        hits = scan_file(raw, file_path, rule, compiled_ranges)

        # Return findings only if matches were found (skip if no hits)
        if hits:
            # Track findings in live findings file if manager is available
            if findings_manager:
                for hit in hits:
                    findings_manager.add_finding(
                        project=project_name,
                        project_url=project_url,
                        branch=branch,
                        file=file_path,
                        file_type=file_type,
                        package=hit["package"],
                        version=hit["version"],
                        matched_rules=hit["matched_rules"],
                        matched_text=hit.get("matched_text", ""),
                    )
            
            return {
                "branch": branch,
                "file": file_path,
                "hits": hits,
            }
        else:
            return None

    except Exception as exc:
        # Log scanning failures but continue scanning other files
        LOGGER.exception("Failed reading or scanning %s@%s:%s", project_id, branch, file_path)
        log_terminal_line(f"[ERROR] {project_id}@{branch}:{file_path} failed: {exc}", ANSI_RED)
        update_stats(errors_seen=1)
        return None


def _scan_branch_files(
    project_id: int,
    branch: str,
    filenames: List[str],
    rule: MatchRule,
    compiled_ranges: List[Tuple[str, "NpmSpec"]],
    project_name: str,
    project_url: str,
    findings_manager: Optional["FindingsManager"] = None,
    max_file_size: int = None,
    max_project_files: int = None,
) -> List[Dict[str, Any]]:
    """Scan all target files in a single branch and return findings.
    
    This function retrieves all matching files in the branch and scans each one
    for the search terms specified in the rule.
    """
    findings = []

    # Get list of all matching files in this branch
    try:
        target_files = list_target_files(project_id, branch, filenames)
    except Exception as exc:
        # If we can't list files, log the error and stop scanning this branch
        LOGGER.exception("Tree scan failed for %s@%s", project_id, branch)
        log_terminal_line(f"[ERROR] {project_id}@{branch} tree scan failed: {exc}", ANSI_RED)
        update_stats(errors_seen=1)
        return findings

    # Scan each file found, respecting the max_project_files limit
    for file_path in target_files:
        # Stop if we've reached the maximum number of files to scan for this project
        if max_project_files is not None and len(findings) >= max_project_files:
            LOGGER.info("Reached max_project_files=%s for %s, stopping file scanning", max_project_files, project_id)
            break

        # Update statistics for progress tracking
        update_stats(files_checked=1)
        LOGGER.debug("Fetching %s@%s:%s", project_id, branch, file_path)

        # Scan this individual file and collect any findings
        finding = _scan_single_file(
            project_id, file_path, branch, rule, compiled_ranges, 
            project_name, project_url, findings_manager, max_file_size
        )
        if finding:
            findings.append(finding)
            # Update statistics: count the number of matches found in this file
            update_stats(matches_found=len(finding["hits"]))

    return findings


def scan_project(
    project: Dict[str, Any],
    rule: MatchRule,
    compiled_ranges: List[Tuple[str, "NpmSpec"]],
    filenames: List[str],
    scan_all_branches: bool,
    branch_patterns: List[str],
    findings_manager: Optional["FindingsManager"] = None,
    max_file_size: int = None,
    max_project_files: int = None,
) -> Dict[str, Any]:
    """Scan a single project for matching files and packages across selected branches."""
    project_id = project["id"]
    project_name = project.get("path_with_namespace", str(project_id))
    project_url = project_web_url(project)

    result = {
        "project": project_name,
        "project_url": project_url,
        "project_id": project_id,
        "scanned_files": 0,
        "scanned_branches": 0,
        "findings": [],
        "error": None,
    }

    log_terminal_line(f"[REPO] Starting {project_name}", ANSI_BLUE)
    LOGGER.info("Starting repository scan: %s", project_name)

    try:
        branches = select_branches_for_project(project, scan_all_branches, branch_patterns)
    except Exception as exc:
        result["error"] = f"branch selection failed: {exc}"
        LOGGER.exception("Branch selection failed for %s", project_name)
        update_stats(errors_seen=1)
        return result

    if not branches:
        result["error"] = "no branches selected"
        LOGGER.warning("No branches selected for %s", project_name)
        update_stats(errors_seen=1)
        return result

    LOGGER.info("Repository %s will scan %s branch(es).", project_name, len(branches))

    for branch in branches:
        result["scanned_branches"] += 1
        update_stats(branches_checked=1)
        log_terminal_line(f"[BRANCH] {project_name} -> {branch}", ANSI_MAGENTA)
        LOGGER.info("Scanning branch %s in repository %s", branch, project_name)

        branch_findings = _scan_branch_files(
            project_id, branch, filenames, rule, compiled_ranges, 
            project_name, project_url, findings_manager, max_file_size, max_project_files
        )
        result["findings"].extend(branch_findings)
        result["scanned_files"] += len(branch_findings)  # Approximate - each finding represents one file

    LOGGER.info(
        "Completed repository scan: %s (branches=%s, files=%s, findings=%s)",
        project_name, result["scanned_branches"], result["scanned_files"], len(result["findings"])
    )
    log_terminal_line(
        f"[DONE] {project_name} branches={result['scanned_branches']} "
        f"files={result['scanned_files']} findings={len(result['findings'])}",
        ANSI_CYAN,
    )
    return result


def _process_scan_result(result: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    """Process and collect a single project's scan result.
    
    Adds the result to the results list if it has findings and no critical error.
    """
    # Only collect results that have findings and didn't encounter a critical error
    if result["findings"] and not result["error"]:
        results.append(result)
        LOGGER.info(
            "Repository %s produced %s finding file(s).",
            result["project"], len(result["findings"])
        )
        log_terminal_line(
            f"[SUMMARY] {result['project']} findings={len(result['findings'])} "
            f"branches={result['scanned_branches']} files={result['scanned_files']}",
            ANSI_GREEN
        )
    elif result["error"]:
        # Log projects that had errors but still completed
        LOGGER.warning("Repository %s completed with error: %s", result["project"], result["error"])
        log_terminal_line(f"[SKIP/ERROR] {result['project']}: {result['error']}", ANSI_YELLOW)


def _validate_environment_variables() -> None:
    """Validate required environment variables."""
    if not GITLAB_URL:
        fail("GITLAB_URL is required")
    if not GITLAB_URL.startswith("https://"):
        fail("GITLAB_URL must use HTTPS (start with https://)")
    if not GITLAB_TOKEN:
        fail("GITLAB_TOKEN is required")


def _validate_required_arguments(packages: List[str], filenames: List[str], workers: int) -> None:
    """Validate required command-line arguments."""
    if not packages:
        fail("At least one --package is required")
    if not filenames:
        fail("At least one --filename is required")
    if workers < 1:
        fail("--workers must be >= 1")


def _validate_and_setup_args(args: argparse.Namespace) -> Tuple[List[str], List[str], List[str], List[str], List[str], List[str], List[str], List[Tuple[str, "NpmSpec"]], MatchRule]:
    """Validate arguments and set up core scanning parameters."""
    # Set request timeout from args
    if args.request_timeout:
        config.REQUEST_TIMEOUT = args.request_timeout
        LOGGER.info("Request timeout set to %s seconds", args.request_timeout)

    # Validate environment variables
    _validate_environment_variables()

    # Normalize argument lists
    packages = normalize_list(args.packages)
    versions = normalize_list(args.versions) if args.versions else []
    ranges = normalize_list(args.ranges) if args.ranges else []
    # Handle filenames default: use package-lock.json if none specified
    filenames = normalize_list(args.filenames) if args.filenames else ["package-lock.json"]
    groups = normalize_list(args.groups) if args.groups else []
    project_filters = normalize_list(args.project_filters) if args.project_filters else []
    branch_patterns = normalize_list(args.branch_patterns) if args.branch_patterns else []

    # Validate required arguments
    _validate_required_arguments(packages, filenames, args.workers)

    # Warn about conflicting branch options
    if args.all_branches and branch_patterns:
        log_terminal_line("NOTE: --all-branches was supplied, so --branch-pattern values will be ignored.", ANSI_YELLOW)
        LOGGER.info("--all-branches overrides --branch-pattern.")

    # Build version matching rules
    compiled_ranges = build_specs(ranges)
    rule = MatchRule(packages=packages, exact_versions=versions, version_ranges=ranges)

    return packages, versions, ranges, filenames, groups, project_filters, branch_patterns, compiled_ranges, rule


def _initialize_scan_state(args: argparse.Namespace, packages: List[str], filenames: List[str], versions: List[str], ranges: List[str]) -> ScanState:
    """Initialize or load scan state for pause/resume functionality.
    
    If --resume is specified, attempts to load a previous state from disk.
    If no previous state exists or --resume was not specified, creates a fresh state.
    """
    if args.resume:
        # Attempt to load state from previous scan
        scan_state = load_state(args.state_file)
        if scan_state is None:
            # No previous state found, start fresh (happens on first run or after --clear-state)
            log_terminal_line("[RESUME] No previous state found, starting fresh scan.", ANSI_YELLOW)
            scan_state = create_initial_state(packages, filenames, versions, ranges)
        else:
            # Resumed successfully, show how many projects were already done
            log_terminal_line(
                f"[RESUME] Resuming scan with {len(scan_state.completed_project_ids)} "
                f"completed project(s).",
                ANSI_CYAN
            )
    else:
        # Not resuming, always create fresh state
        scan_state = create_initial_state(packages, filenames, versions, ranges)

    return scan_state


def _prepare_project_list(args: argparse.Namespace, groups: List[str], project_filters: List[str], scan_state: ScanState) -> List[Dict[str, Any]]:
    """Prepare the list of projects to scan, applying filters and limits.
    
    This function:
    1. Gets all target projects based on groups/filters
    2. Removes already-scanned projects if resuming
    3. Applies maximum project limit if specified
    """
    # Fetch projects from GitLab based on group and filter criteria
    projects = list_target_projects(
        groups=groups,
        include_subgroups=args.include_subgroups,
        include_archived=args.include_archived,
        project_filters=project_filters,
    )

    # If resuming, filter out projects that were already scanned
    # This prevents duplicate scanning and allows interrupted scans to resume cleanly
    if args.resume and scan_state:
        projects = filter_completed_projects(projects, scan_state)

    # Apply maximum projects limit if specified via --max-projects
    # Useful for testing or limiting scope of large scans
    if args.max_projects is not None:
        projects = projects[:args.max_projects]
        LOGGER.info("Limited to %s project(s) via --max-projects", len(projects))

    return projects


def _log_scan_configuration(args: argparse.Namespace, packages: List[str], filenames: List[str], versions: List[str], ranges: List[str], projects: List[Dict[str, Any]]) -> None:
    """Log the scan configuration and project selection for transparency.
    
    This helps users verify their scan parameters are correct before the
    lengthy parallel scan begins. Output is both logged to file and terminal.
    """
    LOGGER.info("Projects selected: %s", len(projects))
    LOGGER.info("Search terms: %s", ", ".join(packages))
    LOGGER.info("Filenames: %s", ", ".join(filenames))
    LOGGER.info("Exact versions: %s", ", ".join(versions) if versions else "(none)")
    LOGGER.info("Version ranges: %s", ", ".join(ranges) if ranges else "(none)")
    LOGGER.info("Workers: %s", args.workers)

    # Log branch scanning mode
    if args.all_branches:
        LOGGER.info("Branch mode: all branches")
        log_terminal_line("[MODE] Branch mode: all branches", ANSI_CYAN)
    elif args.branch_patterns:
        LOGGER.info("Branch mode: pattern filtered (%s)", ", ".join(args.branch_patterns))
        log_terminal_line(f"[MODE] Branch mode: pattern filtered ({', '.join(args.branch_patterns)})", ANSI_CYAN)
    else:
        LOGGER.info("Branch mode: default branch only")
        log_terminal_line("[MODE] Branch mode: default branch only", ANSI_CYAN)

    log_terminal_line(f"[MODE] Filenames: {', '.join(filenames)}", ANSI_CYAN)


def _execute_scan(args: argparse.Namespace, projects: List[Dict[str, Any]], rule: MatchRule, compiled_ranges: List[Tuple[str, "NpmSpec"]], filenames: List[str], scan_state: ScanState, findings_manager: Optional["FindingsManager"] = None) -> List[Dict[str, Any]]:
    """Execute the main scanning loop and return results."""
    total_scanned_files = 0
    total_scanned_branches = 0
    results: List[Dict[str, Any]] = []

    # Set up progress bar with dynamic columns for live updates
    progress = tqdm(
        total=len(projects),
        desc="Scanning repositories",
        unit="repo",
        disable=args.no_progress,
        dynamic_ncols=True,  # Allow progress bar to resize with terminal
    )
    if not args.no_progress:
        progress.set_postfix_str(format_live_summary(len(projects)))

    # Use ThreadPoolExecutor for parallel scanning of projects
    # max_workers=8 by default, can be configured via --workers
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all projects for parallel execution
        future_map = {
            executor.submit(
                scan_project,
                project,
                rule,
                compiled_ranges,
                filenames,
                args.all_branches,
                args.branch_patterns,
                findings_manager,
                max_file_size=args.max_file_size,
                max_project_files=args.max_project_files,
            ): project
            for project in projects
        }

        # Process completed scans as they finish (order doesn't matter for results)
        for future in as_completed(future_map):
            project = future_map[future]
            project_name = project.get("path_with_namespace", str(project.get("id")))

            try:
                result = future.result()
            except Exception as exc:
                # Handle unexpected worker thread failures
                LOGGER.exception("Unexpected worker failure for %s", project_name)
                log_terminal_line(f"[ERROR] {project_name} unexpected worker failure: {exc}", ANSI_RED)
                update_stats(repos_completed=1, errors_seen=1)
                if not args.no_progress:
                    progress.update(1)
                    progress.set_postfix_str(format_live_summary(len(projects)))
                continue

            # Aggregate statistics across all completed projects
            total_scanned_files += result["scanned_files"]
            total_scanned_branches += result["scanned_branches"]

            # Track repositories that have findings (used for statistics)
            repo_has_findings = 1 if result["findings"] else 0
            update_stats(repos_completed=1, repos_with_findings=repo_has_findings)

            # Update scan state with results from this project
            # This tracks progress for pause/resume functionality
            if scan_state:
                update_state_with_result(scan_state, result)

            # Process and log the result
            _process_scan_result(result, results)

            # Update progress bar
            if not args.no_progress:
                progress.update(1)
                progress.set_postfix_str(format_live_summary(len(projects)))

    # Clean up progress bar
    if not args.no_progress:
        progress.close()

    return results


def _output_results(args: argparse.Namespace, projects: List[Dict[str, Any]], results: List[Dict[str, Any]], scan_state: ScanState, findings_manager: Optional["FindingsManager"] = None) -> int:
    """Output scan results and handle final state saving."""
    # Sort results by project name for consistent output
    results.sort(key=lambda r: r["project"])

    # Calculate final statistics
    stats = get_stats_snapshot()
    # Avoid division by zero by ensuring minimum elapsed time of 0.001 seconds
    elapsed = max(time.time() - stats.started_at, 0.001)
    repo_rate = stats.repos_completed / elapsed
    branch_rate = stats.branches_checked / elapsed
    file_rate = stats.files_checked / elapsed

    # Display scan summary
    print("")
    print("=== RESULTS ===")
    print(f"Projects checked: {len(projects)}")
    print(f"Branches checked: {stats.branches_checked}")
    print(f"Files checked: {stats.files_checked}")
    print(f"Projects with findings: {len(results)}")
    print(f"Matches found: {stats.matches_found}")
    print(f"Errors seen: {stats.errors_seen}")
    print(f"Elapsed seconds: {elapsed:.2f}")
    print(f"Throughput: {repo_rate:.2f} repo/s | {branch_rate:.2f} branch/s | {file_rate:.2f} file/s")
    print(f"Log file: {args.log_file}")
    if findings_manager:
        print(f"Findings file: {args.findings_file}")
        findings_summary = findings_manager.get_summary()
        print(f"Total findings: {findings_summary['total_findings']}")
    print("")

    # Handle case where no matches were found
    if not results:
        print("No matches found.")
        # Save state if this is a resumed scan that didn't complete
        # This preserves progress even when no matches are found
        if scan_state and args.resume:
            save_state(scan_state, args.state_file)
        return 0

    # Display detailed results for projects with findings
    for result in results:
        print(f"[FOUND] {result['project']}")
        print(f"  URL:    {result['project_url']}")

        for finding in result["findings"]:
            print(f"  Branch: {finding['branch']}")
            print(f"  File:   {finding['file']}")
            for hit in finding["hits"]:
                print(
                    f"    - package={hit['package']} "
                    f"version={hit['version']} "
                    f"location={hit['location']} "
                    f"matched_by={','.join(hit['matched_rules'])} "
                    f"source={hit['source']}"
                )
        print("")

    # Handle final state saving
    _handle_final_state(scan_state, args, projects)

    return 2


def _handle_final_state(scan_state: ScanState, args: argparse.Namespace, projects: List[Dict[str, Any]]) -> None:
    """Handle final state saving based on scan completion status.
    
    If the scan completed fully, no state file is needed. If it's incomplete,
    save the state so the user can resume later with --resume.
    """
    if not scan_state or len(scan_state.completed_project_ids) == 0:
        return

    total_projects_scanned = len(scan_state.completed_project_ids)
    total_projects_targeted = len(projects)

    if total_projects_scanned >= total_projects_targeted:
        # Scan completed successfully, state file not needed
        LOGGER.info("Scan completed. State file can be cleared with --clear-state.")
    else:
        # Scan incomplete, save state to allow resuming
        save_state(scan_state, args.state_file)


def main() -> int:
    """Main entry point for the GitLab package scanner.
    
    Execution flow:
    1. Parse and validate arguments
    2. Initialize logging (file and console with colors)
    3. Set up signal handler for graceful Ctrl+C interruption
    4. Initialize or load scan state for pause/resume
    5. Initialize findings manager for live findings tracking
    6. Fetch project list from GitLab with filters applied
    7. Execute parallel scan across projects and branches
    8. Output results and save final state if needed
    """
    
    global _current_scan_state, _state_file_path

    # Parse command-line arguments
    args = parse_args()
    setup_logging(args.log_file, args.verbose)

    # Set up signal handler for graceful interrupt (Ctrl+C)
    # Allows saving progress before exit for resumed scans
    _state_file_path = args.state_file
    signal.signal(signal.SIGINT, _handle_interrupt)

    # Handle state management options
    if args.clear_state:
        clear_state(args.state_file)
        log_terminal_line("[STATE] Cleared previous scan state.", ANSI_CYAN)

    # Validate arguments and set up core parameters
    # Normalizes lists, validates required fields, builds version specs
    packages, versions, ranges, filenames, groups, project_filters, branch_patterns, compiled_ranges, rule = _validate_and_setup_args(args)

    # Initialize scan state (new or resumed from previous run)
    _current_scan_state = _initialize_scan_state(args, packages, filenames, versions, ranges)

    # Initialize findings manager for live tracking
    findings_manager = FindingsManager(args.findings_file)
    log_terminal_line(f"[FINDINGS] Live findings will be saved to {args.findings_file}", ANSI_CYAN)

    # Prepare project list (all projects, minus already-scanned if resuming)
    projects = _prepare_project_list(args, groups, project_filters, _current_scan_state)

    # Log configuration for user transparency
    _log_scan_configuration(args, packages, filenames, versions, ranges, projects)

    # Execute the main parallel scanning loop
    # Returns list of projects with findings
    results = _execute_scan(args, projects, rule, compiled_ranges, filenames, _current_scan_state, findings_manager)

    # Output results and handle final state saving
    return _output_results(args, projects, results, _current_scan_state, findings_manager)


if __name__ == "__main__":
    import sys
    sys.exit(main())
