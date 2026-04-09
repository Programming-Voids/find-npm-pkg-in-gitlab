"""
GitLab API interaction functions for the package scanner.
"""

import fnmatch
import requests
import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from . import config
from .utils import LOGGER, log_terminal_line

ANSI_BLUE = "\033[34m"
ANSI_RED = "\033[31m"


def gitlab_get(url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    """Make a GET request to GitLab API with automatic rate limiting handling."""
    resp = config.SESSION.get(url, params=params, timeout=config.REQUEST_TIMEOUT)

    # Handle GitLab API rate limiting (HTTP 429)
    if resp.status_code == 429:
        # Extract retry delay from response header, default to 5 seconds
        retry_after = int(resp.headers.get("Retry-After", "5"))
        LOGGER.warning("Rate limited on %s. Sleeping for %s seconds.", url, retry_after)
        time.sleep(retry_after)
        # Retry the request after waiting
        resp = config.SESSION.get(url, params=params, timeout=config.REQUEST_TIMEOUT)

    return resp


def paginated_get(url: str, params: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
    """Iterate over all pages of a paginated GitLab API response.
    
    GitLab API uses cursor-based pagination with X-Page and X-Total-Pages headers.
    This function automatically handles pagination to retrieve all results.
    """
    page = 1
    per_page = 100  # GitLab API supports up to 100 items per page for efficiency
    while True:
        # Merge user params with pagination params
        merged = dict(params or {})
        merged.update({"page": page, "per_page": per_page})

        resp = gitlab_get(url, merged)
        if not resp.ok:
            raise RuntimeError(f"GET {url} failed: {resp.status_code} {resp.text[:300]}")

        items = resp.json()
        if not items:
            # No more items to return (empty page indicates end of results)
            break

        # Yield each item from this page one at a time
        for item in items:
            yield item

        # Check if there are more pages by looking at GitLab's next page header
        next_page = resp.headers.get("X-Next-Page")
        if not next_page:
            # No more pages available, iteration complete
            break
        page = int(next_page)


def list_membership_projects(include_archived: bool, project_filters: List[str]) -> List[Dict[str, Any]]:
    """List projects the user has membership in, with optional filtering.
    
    This uses the "membership" endpoint to retrieve only projects the user has access to.
    Non-members cannot see projects they don't have permission for, ensuring security.
    """
    url = f"{config.GITLAB_URL}/api/v4/projects"
    params = {
        "membership": True,  # Only projects user is a member of
        "simple": True,  # Simplified response (fewer fields, faster)
        "order_by": "id",  # Sort by project ID for consistent ordering
        "sort": "asc",  # Ascending order
    }

    LOGGER.info("Listing membership projects.")
    # Get all projects user has membership in (handles pagination automatically)
    projects = list(paginated_get(url, params))

    # Filter out archived projects if not including them
    if not include_archived:
        projects = [p for p in projects if not p.get("archived", False)]

    # Apply project name filters (case-insensitive substring matching)
    if project_filters:
        lowered = [f.lower() for f in project_filters]
        projects = [
            p for p in projects
            if any(f in str(p.get("path_with_namespace", "")).lower() for f in lowered)
        ]

    LOGGER.info("Membership project selection complete: %s project(s).", len(projects))
    return projects


def list_group_projects(group: str, include_subgroups: bool, include_archived: bool) -> List[Dict[str, Any]]:
    """List projects in a GitLab group, optionally including subgroups."""
    encoded_group = quote(group, safe="")
    url = f"{config.GITLAB_URL}/api/v4/groups/{encoded_group}/projects"
    params = {
        "simple": True,
        "archived": include_archived,
        "include_subgroups": include_subgroups,
        "order_by": "id",
        "sort": "asc",
    }

    LOGGER.info(
        "Listing projects for group=%s include_subgroups=%s include_archived=%s",
        group, include_subgroups, include_archived
    )
    projects = list(paginated_get(url, params))

    if not include_archived:
        projects = [p for p in projects if not p.get("archived", False)]

    LOGGER.info("Group %s returned %s project(s).", group, len(projects))
    return projects


def list_target_projects(
    groups: List[str],
    include_subgroups: bool,
    include_archived: bool,
    project_filters: List[str],
) -> List[Dict[str, Any]]:
    """Collect all target projects from specified groups or membership, with deduplication."""
    all_projects: Dict[int, Dict[str, Any]] = {}

    if groups:
        for group in groups:
            log_terminal_line(f"[GROUP] Resolving projects for {group}", ANSI_BLUE)
            try:
                projects = list_group_projects(group, include_subgroups, include_archived)
            except Exception as exc:
                LOGGER.exception("Failed to resolve group %s", group)
                log_terminal_line(f"[ERROR] group={group} failed: {exc}", ANSI_RED)
                continue
            for p in projects:
                all_projects[p["id"]] = p
    else:
        projects = list_membership_projects(include_archived, project_filters)
        for p in projects:
            all_projects[p["id"]] = p

    projects = list(all_projects.values())

    if project_filters:
        lowered = [f.lower() for f in project_filters]
        projects = [
            p for p in projects
            if any(f in str(p.get("path_with_namespace", "")).lower() for f in lowered)
        ]

    projects.sort(key=lambda p: p.get("id", 0))
    LOGGER.info("Final project selection: %s project(s).", len(projects))
    return projects


def list_branches(project_id: int) -> List[str]:
    """List all branches for a given project."""
    url = f"{config.GITLAB_URL}/api/v4/projects/{project_id}/repository/branches"
    branches = [b["name"] for b in paginated_get(url)]
    branches.sort()
    return branches


def filter_branches(branches: List[str], branch_patterns: List[str]) -> List[str]:
    """Filter branches using shell-style patterns, removing duplicates."""
    import fnmatch
    if not branch_patterns:
        return branches

    matched: List[str] = []
    seen = set()
    for branch in branches:
        if any(fnmatch.fnmatch(branch, pattern) for pattern in branch_patterns):
            if branch not in seen:
                matched.append(branch)
                seen.add(branch)
    return matched


def select_branches_for_project(
    project: Dict[str, Any],
    scan_all_branches: bool,
    branch_patterns: List[str],
) -> List[str]:
    """Select branches to scan for a project based on options."""
    project_id = project["id"]
    default_branch = project.get("default_branch")

    if scan_all_branches:
        branches = list_branches(project_id)
        LOGGER.debug("Project %s selected %s branch(es) via --all-branches.", project_id, len(branches))
        return branches

    if branch_patterns:
        branches = list_branches(project_id)
        filtered = filter_branches(branches, branch_patterns)
        LOGGER.debug(
            "Project %s selected %s/%s branch(es) via patterns=%s",
            project_id, len(filtered), len(branches), branch_patterns
        )
        return filtered

    return [default_branch] if default_branch else []


def list_target_files(project_id: int, ref: str, filenames: List[str]) -> List[str]:
    """
    Recursively list target files in a project tree.

    Matches by basename, so 'apps/api/package-lock.json' will match --filename package-lock.json.
    """
    url = f"{config.GITLAB_URL}/api/v4/projects/{project_id}/repository/tree"
    params = {
        "ref": ref,
        "recursive": True,
    }

    files: List[str] = []
    filename_set = set(filenames)

    for item in paginated_get(url, params):
        if item.get("type") == "blob" and item.get("name") in filename_set:
            files.append(item["path"])

    return files


def get_file_raw(project_id: int, file_path: str, ref: str, max_size: Optional[int] = None) -> Optional[str]:
    """
    Fetch the raw content of a file from a GitLab repository.
    
    Returns None if file exceeds max_size (if specified).
    """
    encoded_path = quote(file_path, safe="")
    url = f"{config.GITLAB_URL}/api/v4/projects/{project_id}/repository/files/{encoded_path}/raw"

    resp = gitlab_get(url, {"ref": ref})
    if not resp.ok:
        raise RuntimeError(
            f"Failed to fetch {file_path} in project {project_id} at ref {ref}: "
            f"{resp.status_code} {resp.text[:200]}"
        )
    
    content = resp.text
    if max_size is not None and len(content.encode('utf-8')) > max_size:
        LOGGER.debug("File %s exceeds max_size=%s bytes", file_path, max_size)
        return None
    
    return content


def project_web_url(project: Dict[str, Any]) -> str:
    """Get the web URL for a project, falling back to various fields."""
    return (
        project.get("web_url")
        or project.get("http_url_to_repo")
        or project.get("name_with_namespace")
        or str(project.get("id"))
    )
