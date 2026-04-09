"""
File scanning and parsing logic for the GitLab package scanner.

Supports multiple lock file formats:
- package-lock.json (npm)
- yarn.lock (yarn)
- Generic text search for any file

The architecture is extensible to add new lock file formats:
1. Define a parser function: parse_FORMATNAME(content, rule, compiled_ranges) -> List[Dict]
2. Register it in LOCK_FILE_PARSERS mapping
3. Add file detection logic in get_lock_file_format()
"""

import json
from typing import Any, Dict, List, Optional, Tuple, Callable

from semantic_version import NpmSpec, Version

from .utils import LOGGER

# Try importing PyYAML for yarn.lock support
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Try importing toml for poetry.lock support
try:
    import toml
    HAS_TOML = True
except ImportError:
    HAS_TOML = False


def parse_version(version_str: str) -> Optional[Version]:
    """Parse a version string into a semantic version object."""
    try:
        return Version.coerce(version_str, partial=False)
    except ValueError:
        return None


def build_specs(version_ranges: List[str]) -> List[Tuple[str, NpmSpec]]:
    """Compile version range strings into NpmSpec objects."""
    compiled: List[Tuple[str, NpmSpec]] = []
    for raw in version_ranges:
        try:
            compiled.append((raw, NpmSpec(raw)))
        except ValueError as exc:
            from .utils import fail
            fail(f"Invalid version range '{raw}': {exc}")
    return compiled


def extract_matched_text(content: str, package_name: str, version: str, file_type: str = "generic") -> Optional[str]:
    """Extract the matched text from file content for reporting.
    
    Attempts to find and return the relevant line(s) that contain the match.
    For structured files, returns a JSON/YAML/TOML snippet.
    For text files, returns the matching line(s).
    
    Args:
        content: File content
        package_name: Package name to search for
        version: Version to search for
        file_type: Type of file (generic, package-lock.json, etc.)
    
    Returns:
        Matched text snippet or None if not found
    """
    lines = content.split('\n')
    
    # For each line, check if it contains both package and version
    for i, line in enumerate(lines):
        if package_name in line:
            # Check if version is also in this line or nearby lines
            context_start = max(0, i - 1)
            context_end = min(len(lines), i + 2)
            context = '\n'.join(lines[context_start:context_end])
            
            if version in context or version.lstrip('=<>!~^') in context:
                # Return the matched line with some context
                return line.strip()
    
    # If not found, try to find just the package name
    for line in lines:
        if package_name in line:
            return line.strip()[:200]  # Limit to 200 chars
    
    return None



def version_matches(
    installed_version: str,
    exact_versions: List[str],
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> Tuple[bool, List[str]]:
    """Check if an installed version matches any of the specified exact versions or ranges."""
    matched_rules: List[str] = []

    # Check for exact version matches first (fast string comparison)
    if exact_versions and installed_version in exact_versions:
        matched_rules.append(f"exact:{installed_version}")

    # Check semantic version ranges if any are specified
    if compiled_ranges:
        parsed = parse_version(installed_version)
        if parsed is not None:
            # Test against each compiled range specification
            for raw_range, spec in compiled_ranges:
                if spec.match(parsed):
                    matched_rules.append(f"range:{raw_range}")

    # If no specific versions or ranges were requested, match any version
    if not exact_versions and not compiled_ranges:
        matched_rules.append("any-version")

    # Return whether any rules matched and which ones
    return (len(matched_rules) > 0), matched_rules


def package_path_matches(pkg_path: str, package_name: str) -> bool:
    """Check if a package path corresponds to the given package name in node_modules."""
    suffix = f"node_modules/{package_name}"
    return pkg_path == suffix or pkg_path.endswith("/" + suffix)


def find_in_packages_map(
    lock_data: Dict[str, Any],
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Search for matches in the packages map of a package-lock.json file.
    
    The 'packages' map is the modern npm lock file format that lists all installed
    packages flat with their paths (e.g., "node_modules/axios").
    """
    hits: List[Dict[str, Any]] = []
    packages = lock_data.get("packages")

    # Validate that packages is a dict; some files may have missing or malformed packages
    if not isinstance(packages, dict):
        return hits

    # Iterate through each package entry in the packages map
    for pkg_path, meta in packages.items():
        # Skip invalid entries (entries must have string paths and dict metadata)
        if not isinstance(pkg_path, str) or not isinstance(meta, dict):
            continue

        # Extract the installed version from package metadata
        installed_version = meta.get("version")
        # Skip entries without a version field
        if not isinstance(installed_version, str):
            continue

        # Check each search term against this package
        for package_name in rule.packages:
            # Check if the package path belongs to this package name
            if package_path_matches(pkg_path, package_name):
                # Test if version matches any of the specified criteria
                matched, matched_rules = version_matches(
                    installed_version,
                    rule.exact_versions,
                    compiled_ranges,
                )
                # If version matches, record the hit
                if matched:
                    hits.append(
                        {
                            "package": package_name,
                            "version": installed_version,
                            "location": pkg_path,
                            "matched_rules": matched_rules,
                            "source": "package-lock.json",
                        }
                    )

    return hits


def _process_dependency_node(
    dep_name: str,
    meta: Dict[str, Any],
    current_path: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Process a single dependency node and return any matches found."""
    hits: List[Dict[str, Any]] = []

    installed_version = meta.get("version")
    if dep_name in rule.packages and isinstance(installed_version, str):
        matched, matched_rules = version_matches(
            installed_version,
            rule.exact_versions,
            compiled_ranges,
        )
        if matched:
            hits.append(
                {
                    "package": dep_name,
                    "version": installed_version,
                    "location": current_path,
                    "matched_rules": matched_rules,
                    "source": "package-lock.json",
                }
            )

    return hits


def find_in_dependencies_tree(
    node: Any,
    trail: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Recursively search for matches in the dependencies tree of a package-lock.json file."""
    hits: List[Dict[str, Any]] = []

    if not isinstance(node, dict):
        return hits

    dependencies = node.get("dependencies")
    if not isinstance(dependencies, dict):
        return hits

    for dep_name, meta in dependencies.items():
        current_path = f"{trail}/{dep_name}" if trail else dep_name

        if isinstance(meta, dict):
            # Process this dependency node
            hits.extend(_process_dependency_node(dep_name, meta, current_path, rule, compiled_ranges))

            # Recursively process child dependencies
            hits.extend(find_in_dependencies_tree(meta, current_path, rule, compiled_ranges))
        else:
            # Skip non-dict metadata
            continue

    return hits


def dedupe_hits(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate hits based on package, version, location, rules, and source."""
    seen = set()
    deduped: List[Dict[str, Any]] = []

    for hit in hits:
        key = (
            hit["package"],
            hit["version"],
            hit["location"],
            tuple(sorted(hit["matched_rules"])),
            hit["source"],
        )
        if key not in seen:
            seen.add(key)
            deduped.append(hit)

    return deduped


# ============================================================================
# PACKAGE-LOCK.JSON PARSER (npm)
# ============================================================================

def parse_package_lock_json(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a package-lock.json file for matching packages and versions."""
    try:
        lock_data = json.loads(content)
    except json.JSONDecodeError:
        LOGGER.warning("Skipped malformed package-lock.json content.")
        return []

    hits: List[Dict[str, Any]] = []
    hits.extend(find_in_packages_map(lock_data, rule, compiled_ranges))
    hits.extend(find_in_dependencies_tree(lock_data, "", rule, compiled_ranges))
    return dedupe_hits(hits)


# ============================================================================
# YARN.LOCK PARSER (yarn)
# ============================================================================

def _extract_yarn_package_info(entry_text: str) -> Optional[Tuple[str, str]]:
    """Extract package name and version from a yarn.lock entry.
    
    Yarn.lock entries look like:
      package-name@^1.0.0, package-name@>=1.0.0:
        version "1.2.3"
        ...
    
    Returns: (package_name, version) or None if parsing fails
    """
    if not entry_text or ":" not in entry_text:
        return None
    
    # Get the part before the colon (the dependency specifiers)
    specifier_part = entry_text.split(":")[0].strip()
    
    # Split by commas in case there are multiple specifiers for the same package
    # We only care about the first one to get the package name
    first_spec = specifier_part.split(",")[0].strip()
    
    # Extract package name by removing version specifiers (@^1.0.0 → package-name)
    if "@" not in first_spec:
        return None
    
    # Find the last @ which separates package name from version spec
    last_at_idx = first_spec.rfind("@")
    if last_at_idx <= 0:
        return None
    
    package_name = first_spec[:last_at_idx]
    return package_name


def parse_yarn_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a yarn.lock file for matching packages and versions.
    
    Yarn.lock is a text-based lock file format with entries like:
      package-name@^1.0.0:
        version "1.2.3"
        resolved "https://registry.npmjs.org/package-name/-/package-name-1.2.3.tgz"
    """
    if not HAS_YAML:
        LOGGER.warning("PyYAML not installed. Cannot parse yarn.lock with structured parsing. Falling back to text search.")
        return []
    
    try:
        # Parse YAML to extract version metadata
        lock_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        LOGGER.warning("Failed to parse yarn.lock as YAML: %s. Falling back to text search.", e)
        return []
    
    if not isinstance(lock_data, dict):
        LOGGER.warning("yarn.lock parsed but is not a dictionary. Falling back to text search.")
        return []
    
    hits: List[Dict[str, Any]] = []
    
    # Iterate through yarn.lock entries
    # Each entry is keyed by "package@specifier" and contains metadata including version
    for entry_key, entry_data in lock_data.items():
        if not isinstance(entry_data, dict):
            continue
        
        # Extract package name and target version from entry metadata
        installed_version = entry_data.get("version")
        if not isinstance(installed_version, str):
            continue
        
        # Parse the entry key to get the package name
        package_name = _extract_yarn_package_info(entry_key)
        if not package_name:
            continue
        
        # Check if this package is in our search list
        if package_name not in rule.packages:
            continue
        
        # Test if version matches any of the specified criteria
        matched, matched_rules = version_matches(
            installed_version,
            rule.exact_versions,
            compiled_ranges,
        )
        
        # If version matches, record the hit
        if matched:
            hits.append(
                {
                    "package": package_name,
                    "version": installed_version,
                    "location": f"yarn.lock:{entry_key}",
                    "matched_rules": matched_rules,
                    "source": "yarn.lock",
                }
            )
    
    return dedupe_hits(hits)


# ============================================================================
# PIPFILE.LOCK PARSER (Pipenv/Python)
# ============================================================================

def parse_pipfile_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a Pipfile.lock file for matching packages.
    
    Pipfile.lock is JSON format with sections for 'default' and 'develop' dependencies.
    Each dependency contains a version specification.
    """
    try:
        lock_data = json.loads(content)
    except json.JSONDecodeError:
        LOGGER.warning("Skipped malformed Pipfile.lock content.")
        return []
    
    hits: List[Dict[str, Any]] = []
    
    # Check both default and develop sections
    for section in ["default", "develop"]:
        dependencies = lock_data.get(section, {})
        if not isinstance(dependencies, dict):
            continue
        
        for package_name, meta in dependencies.items():
            if not isinstance(meta, dict):
                continue
            
            # Extract version from version field or pinned version
            version_str = meta.get("version", "")
            if not version_str or not isinstance(version_str, str):
                continue
            
            # Remove leading == or other operators
            installed_version = version_str.lstrip("=<>!~^").strip()
            if not installed_version:
                continue
            
            # Check if this package is in our search list
            if package_name not in rule.packages:
                continue
            
            # Test if version matches
            matched, matched_rules = version_matches(
                installed_version,
                rule.exact_versions,
                compiled_ranges,
            )
            
            if matched:
                hits.append({
                    "package": package_name,
                    "version": installed_version,
                    "location": f"Pipfile.lock:{section}",
                    "matched_rules": matched_rules,
                    "source": "Pipfile.lock",
                })
    
    return dedupe_hits(hits)


# ============================================================================
# POETRY.LOCK PARSER (Poetry/Python)
# ============================================================================

def parse_poetry_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a poetry.lock file for matching packages.
    
    poetry.lock is TOML format with [[package]] sections for each dependency.
    """
    if not HAS_TOML:
        LOGGER.warning("toml library not installed. Cannot parse poetry.lock. Falling back to text search.")
        return []
    
    try:
        lock_data = toml.loads(content)
    except Exception as e:
        LOGGER.warning("Failed to parse poetry.lock as TOML: %s. Falling back to text search.", e)
        return []
    
    hits: List[Dict[str, Any]] = []
    packages = lock_data.get("package", [])
    
    if not isinstance(packages, list):
        return []
    
    for package_entry in packages:
        if not isinstance(package_entry, dict):
            continue
        
        package_name = package_entry.get("name")
        version = package_entry.get("version")
        
        if not package_name or not version or not isinstance(version, str):
            continue
        
        # Check if this package is in our search list
        if package_name not in rule.packages:
            continue
        
        # Test if version matches
        matched, matched_rules = version_matches(
            version,
            rule.exact_versions,
            compiled_ranges,
        )
        
        if matched:
            hits.append({
                "package": package_name,
                "version": version,
                "location": "poetry.lock",
                "matched_rules": matched_rules,
                "source": "poetry.lock",
            })
    
    return dedupe_hits(hits)


# ============================================================================
# GO.SUM PARSER (Go modules)
# ============================================================================

def parse_go_sum(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a go.sum file for matching packages.
    
    go.sum is a text format with lines like:
      module-name version hash
      github.com/user/module v1.2.3 h1:hash
    """
    hits: List[Dict[str, Any]] = []
    lines = content.split('\n')
    seen_modules = set()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # go.sum format: module version hash
        parts = line.split()
        if len(parts) < 2:
            continue
        
        module_name = parts[0]
        version = parts[1]
        
        # Skip if we've already processed this module (go.sum has duplicates)
        module_key = (module_name, version)
        if module_key in seen_modules:
            continue
        seen_modules.add(module_key)
        
        # Check if this package is in our search list
        if module_name not in rule.packages:
            continue
        
        # Test if version matches
        matched, matched_rules = version_matches(
            version,
            rule.exact_versions,
            compiled_ranges,
        )
        
        if matched:
            hits.append({
                "package": module_name,
                "version": version,
                "location": "go.sum",
                "matched_rules": matched_rules,
                "source": "go.sum",
            })
    
    return dedupe_hits(hits)


# ============================================================================
# CARGO.LOCK PARSER (Rust)
# ============================================================================

def parse_cargo_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a Cargo.lock file for matching packages.
    
    Cargo.lock is TOML format with [[package]] sections for each dependency.
    """
    if not HAS_TOML:
        LOGGER.warning("toml library not installed. Cannot parse Cargo.lock. Falling back to text search.")
        return []
    
    try:
        lock_data = toml.loads(content)
    except Exception as e:
        LOGGER.warning("Failed to parse Cargo.lock as TOML: %s. Falling back to text search.", e)
        return []
    
    hits: List[Dict[str, Any]] = []
    packages = lock_data.get("package", [])
    
    if not isinstance(packages, list):
        return []
    
    for package_entry in packages:
        if not isinstance(package_entry, dict):
            continue
        
        package_name = package_entry.get("name")
        version = package_entry.get("version")
        
        if not package_name or not version or not isinstance(version, str):
            continue
        
        # Check if this package is in our search list
        if package_name not in rule.packages:
            continue
        
        # Test if version matches
        matched, matched_rules = version_matches(
            version,
            rule.exact_versions,
            compiled_ranges,
        )
        
        if matched:
            hits.append({
                "package": package_name,
                "version": version,
                "location": "Cargo.lock",
                "matched_rules": matched_rules,
                "source": "Cargo.lock",
            })
    
    return dedupe_hits(hits)


# ============================================================================
# COMPOSER.LOCK PARSER (PHP)
# ============================================================================

def parse_composer_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a composer.lock file for matching packages.
    
    composer.lock is JSON format with "packages" and "packages-dev" arrays.
    """
    try:
        lock_data = json.loads(content)
    except json.JSONDecodeError:
        LOGGER.warning("Skipped malformed composer.lock content.")
        return []
    
    hits: List[Dict[str, Any]] = []
    
    # Check both packages and packages-dev sections
    for section_name in ["packages", "packages-dev"]:
        packages = lock_data.get(section_name, [])
        if not isinstance(packages, list):
            continue
        
        for package_entry in packages:
            if not isinstance(package_entry, dict):
                continue
            
            package_name = package_entry.get("name")
            version = package_entry.get("version")
            
            if not package_name or not version or not isinstance(version, str):
                continue
            
            # Check if this package is in our search list
            # Note: composer uses vendor/package format
            if package_name not in rule.packages:
                # Also check without vendor prefix
                if "/" in package_name:
                    short_name = package_name.split("/", 1)[1]
                    if short_name not in rule.packages:
                        continue
                else:
                    continue
            
            # Test if version matches
            matched, matched_rules = version_matches(
                version,
                rule.exact_versions,
                compiled_ranges,
            )
            
            if matched:
                hits.append({
                    "package": package_name,
                    "version": version,
                    "location": f"composer.lock:{section_name}",
                    "matched_rules": matched_rules,
                    "source": "composer.lock",
                })
    
    return dedupe_hits(hits)


# ============================================================================
# GEMFILE.LOCK PARSER (Ruby)
# ============================================================================

def parse_gemfile_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a Gemfile.lock file for matching packages.
    
    Gemfile.lock is a text format with entries like:
      GEM
        remote: https://rubygems.org/
        specs:
          gem-name (1.2.3)
            dependency (>= 0)
    """
    hits: List[Dict[str, Any]] = []
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for gem entries (indented with spaces, contain version in parentheses)
        if line and not line.startswith('remote:') and '(' in line and ')' in line:
            # Parse format: gem-name (version)
            parts = line.split('(')
            if len(parts) >= 2:
                gem_name = parts[0].strip()
                version_part = parts[1].strip()
                
                # Extract version number (handle formats like "1.2.3", ">= 1.0")
                if ')' in version_part:
                    version = version_part.split(')')[0].strip()
                    
                    # Remove common version operators for matching
                    clean_version = version.lstrip('=<>!~^').strip()
                    
                    # Check if this gem is in our search list
                    if gem_name not in rule.packages:
                        i += 1
                        continue
                    
                    # Test if version matches
                    matched, matched_rules = version_matches(
                        clean_version,
                        rule.exact_versions,
                        compiled_ranges,
                    )
                    
                    if matched:
                        hits.append({
                            "package": gem_name,
                            "version": clean_version,
                            "location": "Gemfile.lock",
                            "matched_rules": matched_rules,
                            "source": "Gemfile.lock",
                        })
        
        i += 1
    
    return dedupe_hits(hits)


# ============================================================================
# GRADLE.LOCK PARSER (Gradle/Java)
# ============================================================================

def parse_gradle_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a gradle.lock file for matching packages.
    
    gradle.lock is a text format with entries like:
      group:artifact:version=locked-version
      com.google.guava:guava:31.1-jre=31.1-android-jre
    """
    hits: List[Dict[str, Any]] = []
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Parse format: group:artifact:requestedVersion=lockedVersion
        if '=' in line:
            parts = line.split('=')
            if len(parts) < 2:
                continue
            
            dependency_spec = parts[0].strip()
            locked_version = parts[1].strip()
            
            # Parse dependency spec: group:artifact:requestedVersion
            dep_parts = dependency_spec.split(':')
            if len(dep_parts) < 2:
                continue
            
            artifact_id = dep_parts[1]
            
            # Check if this package is in our search list
            if artifact_id not in rule.packages:
                continue
            
            # Test if version matches
            matched, matched_rules = version_matches(
                locked_version,
                rule.exact_versions,
                compiled_ranges,
            )
            
            if matched:
                hits.append({
                    "package": artifact_id,
                    "version": locked_version,
                    "location": "gradle.lock",
                    "matched_rules": matched_rules,
                    "source": "gradle.lock",
                })
    
    return dedupe_hits(hits)


# ============================================================================
# PUBSPEC.LOCK PARSER (Pub/Dart)
# ============================================================================

def parse_pubspec_lock(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a pubspec.lock file for matching packages.
    
    pubspec.lock is YAML format with package entries like:
      package_name:
        version: "1.2.3"
    """
    if not HAS_YAML:
        LOGGER.warning("PyYAML not installed. Cannot parse pubspec.lock. Falling back to text search.")
        return []
    
    try:
        lock_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        LOGGER.warning("Failed to parse pubspec.lock as YAML: %s. Falling back to text search.", e)
        return []
    
    if not isinstance(lock_data, dict):
        LOGGER.warning("pubspec.lock parsed but is not a dictionary. Falling back to text search.")
        return []
    
    hits: List[Dict[str, Any]] = []
    
    # Iterate through packages in pubspec.lock
    for package_name, package_info in lock_data.items():
        if not isinstance(package_info, dict):
            continue
        
        version = package_info.get("version")
        if not version or not isinstance(version, str):
            continue
        
        # Check if this package is in our search list
        if package_name not in rule.packages:
            continue
        
        # Test if version matches
        matched, matched_rules = version_matches(
            version,
            rule.exact_versions,
            compiled_ranges,
        )
        
        if matched:
            hits.append({
                "package": package_name,
                "version": version,
                "location": "pubspec.lock",
                "matched_rules": matched_rules,
                "source": "pubspec.lock",
            })
    
    return dedupe_hits(hits)


# ============================================================================
# REQUIREMENTS.TXT PARSER (pip/Python)
# ============================================================================

def parse_requirements_txt(
    content: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a requirements.txt or requirements.lock file.
    
    Format: package-name==version or package-name>=version, etc.
    """
    hits: List[Dict[str, Any]] = []
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
        
        # Parse requirement line
        package_name = None
        version = None
        
        # Handle formats like:
        # - package==1.2.3
        # - package>=1.0,<2.0
        # - package[extra]==1.2.3
        
        # Remove extras in brackets
        if '[' in line:
            line = line.split('[')[0] + line.split(']')[1] if ']' in line else line.split('[')[0]
        
        # Check for version specifiers
        for operator in ['==', '>=', '<=', '>', '<', '~=', '!=']: 
            if operator in line:
                parts = line.split(operator, 1)
                package_name = parts[0].strip()
                version_part = parts[1].strip()
                
                # Handle multiple constraints like >=1.0,<2.0
                if ',' in version_part:
                    version = version_part.split(',')[0].strip()
                else:
                    version = version_part.strip()
                break
        
        if not package_name or not version:
            continue
        
        # Check if this package is in our search list
        if package_name not in rule.packages:
            continue
        
        # Test if version matches
        matched, matched_rules = version_matches(
            version,
            rule.exact_versions,
            compiled_ranges,
        )
        
        if matched:
            hits.append({
                "package": package_name,
                "version": version,
                "location": "requirements.txt",
                "matched_rules": matched_rules,
                "source": "requirements.txt",
            })
    
    return dedupe_hits(hits)


# ============================================================================
# LOCK FILE FORMAT DETECTION AND ROUTING
# ============================================================================

def get_lock_file_format(file_path: str) -> Optional[str]:
    """Determine the lock file format based on filename.
    
    Supports: package-lock.json, yarn.lock, poetry.lock, Pipfile.lock,
    go.sum, Cargo.lock, composer.lock, Gemfile.lock, gradle.lock,
    pubspec.lock, requirements.txt, requirements.lock
    
    To add a new lock file format:
    1. Add detection logic here (return format name)
    2. Create a parser function: parse_FORMATNAME(content, rule, compiled_ranges)
    3. Register in LOCK_FILE_PARSERS below
    4. Add tests
    """
    if file_path.endswith("package-lock.json"):
        return "package-lock.json"
    elif file_path.endswith("yarn.lock"):
        return "yarn.lock"
    elif file_path.endswith("poetry.lock"):
        return "poetry.lock"
    elif file_path.endswith("Pipfile.lock"):
        return "Pipfile.lock"
    elif file_path.endswith("go.sum"):
        return "go.sum"
    elif file_path.endswith("Cargo.lock"):
        return "Cargo.lock"
    elif file_path.endswith("composer.lock"):
        return "composer.lock"
    elif file_path.endswith("Gemfile.lock"):
        return "Gemfile.lock"
    elif file_path.endswith("gradle.lock"):
        return "gradle.lock"
    elif file_path.endswith("pubspec.lock"):
        return "pubspec.lock"
    elif file_path.endswith("requirements.lock") or file_path.endswith("requirements.txt"):
        return "requirements.txt"
    
    return None


# Parser registry: maps format name to parser function
# To add a new format, create a parser function and add it here
LOCK_FILE_PARSERS: Dict[str, Callable] = {
    "package-lock.json": parse_package_lock_json,
    "yarn.lock": parse_yarn_lock,
    "poetry.lock": parse_poetry_lock,
    "Pipfile.lock": parse_pipfile_lock,
    "go.sum": parse_go_sum,
    "Cargo.lock": parse_cargo_lock,
    "composer.lock": parse_composer_lock,
    "Gemfile.lock": parse_gemfile_lock,
    "gradle.lock": parse_gradle_lock,
    "pubspec.lock": parse_pubspec_lock,
    "requirements.txt": parse_requirements_txt,
}


def should_parse_as_package_lock(file_path: str) -> bool:
    """Check if a file path indicates it should be parsed as a structured lock file."""
    return get_lock_file_format(file_path) is not None


# ============================================================================
# STRUCTURED LOCK FILE PARSING (GENERIC DISPATCHER)
# ============================================================================

def scan_structured_lock_file(
    content: str,
    file_path: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a structured lock file (package-lock.json, yarn.lock, etc).
    
    Routes to the appropriate parser based on file format.
    Falls back to generic text search if structured parsing fails.
    """
    lock_format = get_lock_file_format(file_path)
    
    if lock_format not in LOCK_FILE_PARSERS:
        # Should not happen if get_lock_file_format() is correctly implemented
        LOGGER.debug("No parser for lock file format: %s", lock_format)
        return []
    
    parser = LOCK_FILE_PARSERS[lock_format]
    try:
        hits = parser(content, rule, compiled_ranges)
        if hits:
            return hits
    except Exception as e:
        LOGGER.warning("Structured parsing failed for %s: %s. Falling back to text search.", lock_format, e)
    
    # If structured parsing failed or found nothing,fall through to generic text search
    return []


# ============================================================================
# GENERIC TEXT FILE PARSING
# ============================================================================

def _check_version_matches_in_text(content: str, rule: "MatchRule") -> List[str]:
    """Check if any specified versions or ranges appear in the content as literal text."""
    matched_rules: List[str] = []

    # For generic files, we do simple substring matching for versions
    # This is less sophisticated than semantic version matching but works for any file type
    for version in rule.exact_versions:
        if version in content:
            matched_rules.append(f"text-version:{version}")

    # Version ranges are also matched as literal strings in generic files
    for version_range in rule.version_ranges:
        if version_range in content:
            matched_rules.append(f"text-range:{version_range}")

    return matched_rules


def scan_generic_file(content: str, rule: "MatchRule") -> List[Dict[str, Any]]:
    """
    Generic text-based search for any search terms in any file.

    Behavior:
    - If versions/ranges are supplied, try to require both the term and at least one version/range text.
    - For version ranges in generic files, we do a literal text match on the range string.
    - If no versions/ranges are supplied, any term match is reported.
    """
    hits: List[Dict[str, Any]] = []

    for package in rule.packages:
        # Skip packages that don't appear in the content at all
        if package not in content:
            continue

        # Check if any specified versions appear in the text
        matched_rules = _check_version_matches_in_text(content, rule)

        # Determine if we have a valid match based on version requirements
        if rule.exact_versions or rule.version_ranges:
            # Versions/ranges specified - require at least one version match
            # This ensures we don't report false positives when specific versions are requested
            if not matched_rules:
                continue
            # else: we have matched_rules, so proceed with the hit
        else:
            # No versions specified, so any package match is valid
            # This allows broad searches when you just want to find packages regardless of version
            matched_rules.append("text")

        # Record the finding
        hits.append(
            {
                "package": package,
                "version": "unknown",  # Generic files don't have structured version info
                "location": "text-match",  # Generic location indicator
                "matched_rules": matched_rules,
                "source": "generic",  # Indicates this came from generic text search
            }
        )

    return dedupe_hits(hits)


# ============================================================================
# PUBLIC SCANNING API
# ============================================================================

def scan_file(
    content: str,
    file_path: str,
    rule: "MatchRule",
    compiled_ranges: List[Tuple[str, NpmSpec]],
) -> List[Dict[str, Any]]:
    """Scan a file for matching packages.
    
    Attempts structured parsing if the file is a known lock file format.
    Falls back to generic text search for unknown formats.
    Includes matched text for each finding.
    """
    # Try structured parsing first if it's a known lock file
    if should_parse_as_package_lock(file_path):
        hits = scan_structured_lock_file(content, file_path, rule, compiled_ranges)
        if hits:
            # Add matched text to each hit
            for hit in hits:
                if not hit.get("matched_text"):
                    hit["matched_text"] = extract_matched_text(
                        content,
                        hit["package"],
                        hit["version"],
                        hit.get("source", "generic"),
                    )
            return hits
        # If structured parsing found nothing, fall through to generic search
    
    # Generic text-based search (always available as fallback)
    hits = scan_generic_file(content, rule)
    
    # Add matched text to each hit from generic search
    for hit in hits:
        if not hit.get("matched_text"):
            hit["matched_text"] = extract_matched_text(
                content,
                hit["package"],
                hit.get("version", "unknown"),
                "generic",
            )
    
    return hits
