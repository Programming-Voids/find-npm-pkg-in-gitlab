#!/usr/bin/env python3
"""
Comprehensive tests for all lock file format parsers.
Tests each parser's ability to extract package names and versions correctly.
"""

import sys
import os
import json

# Add parent directory to path so we can import the package
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(parent_dir))

# Get package name from folder
package_name = os.path.basename(parent_dir)


def test_pipfile_lock_parser():
    """Test Pipenv Pipfile.lock parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    # Test 1: Parse Pipfile.lock with default dependencies
    try:
        pipfile_lock = {
            "default": {
                "requests": {"version": "==2.28.1"},
                "django": {"version": "==4.1.0"}
            },
            "develop": {
                "pytest": {"version": "==7.1.2"}
            }
        }
        content = json.dumps(pipfile_lock)
        # Search for packages without version constraints to test basic parsing
        rule = MatchRule(packages=["requests", "django"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_pipfile_lock(content, rule, compiled_ranges)
        
        assert len(results) > 0, "Should find matches"
        assert any(x["package"] == "requests" and x["version"] == "2.28.1" for x in results), "Should find requests 2.28.1"
        assert any(x["package"] == "django" and x["version"] == "4.1.0" for x in results), "Should find django 4.1.0"
        print("✓ Parse Pipfile.lock with default dependencies")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse Pipfile.lock with default dependencies: {e}")
        tests_failed += 1

    # Test 2: Parse Pipfile.lock with develop dependencies
    try:
        pipfile_lock = {
            "default": {"requests": {"version": "==2.28.1"}},
            "develop": {"pytest": {"version": "==7.1.2"}}
        }
        content = json.dumps(pipfile_lock)
        rule = MatchRule(packages=["pytest"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_pipfile_lock(content, rule, compiled_ranges)
        
        assert any(r["package"] == "pytest" and r["source"] == "Pipfile.lock" for r in results)
        print("✓ Parse Pipfile.lock with develop dependencies")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse Pipfile.lock with develop dependencies: {e}")
        tests_failed += 1

    # Test 3: Parse malformed Pipfile.lock (should not crash)
    try:
        rule = MatchRule(packages=["requests"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        results = scanner.parse_pipfile_lock("invalid json", rule, compiled_ranges)
        assert results == []
        print("✓ Parse malformed Pipfile.lock")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse malformed Pipfile.lock: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_poetry_lock_parser():
    """Test Poetry poetry.lock parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    # Check if toml is available
    if not scanner.HAS_TOML:
        print("⊘ Poetry.lock tests skipped (toml library not installed)")
        return 1, 0

    # Test 1: Parse poetry.lock with single package
    try:
        import toml
        poetry_lock = {
            "package": [
                {"name": "requests", "version": "2.28.1"},
                {"name": "django", "version": "4.1.0"}
            ]
        }
        content = toml.dumps(poetry_lock)
        rule = MatchRule(packages=["requests"], exact_versions=["2.28.1"], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_poetry_lock(content, rule, compiled_ranges)
        
        assert any(x["package"] == "requests" and x["version"] == "2.28.1" for x in results)
        assert results[0]["source"] == "poetry.lock"
        print("✓ Parse poetry.lock with single package")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse poetry.lock with single package: {e}")
        tests_failed += 1

    # Test 2: Parse poetry.lock with multiple packages
    try:
        import toml
        poetry_lock = {
            "package": [
                {"name": "requests", "version": "2.28.1"},
                {"name": "django", "version": "4.1.0"},
                {"name": "flask", "version": "2.1.2"}
            ]
        }
        content = toml.dumps(poetry_lock)
        rule = MatchRule(packages=["requests", "django", "flask"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_poetry_lock(content, rule, compiled_ranges)
        
        assert len(results) == 3
        print("✓ Parse poetry.lock with multiple packages")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse poetry.lock with multiple packages: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_go_sum_parser():
    """Test Go go.sum parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    # Test 1: Parse go.sum with single module
    try:
        go_sum_content = """github.com/user/module v1.2.3 h1:hash1
github.com/other/lib v0.5.0 h1:hash2
"""
        rule = MatchRule(packages=["github.com/user/module"], exact_versions=["v1.2.3"], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_go_sum(go_sum_content, rule, compiled_ranges)
        
        assert any(x["package"] == "github.com/user/module" and x["version"] == "v1.2.3" for x in results)
        assert results[0]["source"] == "go.sum"
        print("✓ Parse go.sum with single module")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse go.sum with single module: {e}")
        tests_failed += 1

    # Test 2: Parse go.sum with multiple modules
    try:
        go_sum_content = """github.com/google/uuid v1.3.0 h1:hash1
github.com/stretchr/testify v1.8.0 h1:hash2
github.com/sirupsen/logrus v1.9.0 h1:hash3
"""
        rule = MatchRule(packages=["github.com/google/uuid", "github.com/stretchr/testify"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_go_sum(go_sum_content, rule, compiled_ranges)
        
        assert len(results) == 2
        print("✓ Parse go.sum with multiple modules")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse go.sum with multiple modules: {e}")
        tests_failed += 1

    # Test 3: Parse empty go.sum
    try:
        rule = MatchRule(packages=["any"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        results = scanner.parse_go_sum("", rule, compiled_ranges)
        assert results == []
        print("✓ Parse empty go.sum")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse empty go.sum: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_cargo_lock_parser():
    """Test Rust Cargo.lock parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    if not scanner.HAS_TOML:
        print("⊘ Cargo.lock tests skipped (toml library not installed)")
        return 1, 0

    # Test 1: Parse Cargo.lock with single crate
    try:
        import toml
        cargo_lock = {
            "package": [
                {"name": "serde", "version": "1.0.147"},
                {"name": "tokio", "version": "1.21.0"}
            ]
        }
        content = toml.dumps(cargo_lock)
        rule = MatchRule(packages=["serde"], exact_versions=["1.0.147"], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_cargo_lock(content, rule, compiled_ranges)
        
        assert any(x["package"] == "serde" and x["version"] == "1.0.147" for x in results)
        assert results[0]["source"] == "Cargo.lock"
        print("✓ Parse Cargo.lock with single crate")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse Cargo.lock with single crate: {e}")
        tests_failed += 1

    # Test 2: Parse Cargo.lock with multiple crates
    try:
        import toml
        cargo_lock = {
            "package": [
                {"name": "serde", "version": "1.0.147"},
                {"name": "tokio", "version": "1.21.0"},
                {"name": "uuid", "version": "1.1.2"}
            ]
        }
        content = toml.dumps(cargo_lock)
        rule = MatchRule(packages=["serde", "tokio", "uuid"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_cargo_lock(content, rule, compiled_ranges)
        
        assert len(results) == 3
        print("✓ Parse Cargo.lock with multiple crates")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse Cargo.lock with multiple crates: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_composer_lock_parser():
    """Test PHP composer.lock parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    # Test 1: Parse composer.lock with packages
    try:
        composer_lock = {
            "packages": [
                {"name": "symfony/console", "version": "5.4.0"},
                {"name": "monolog/monolog", "version": "2.8.0"}
            ],
            "packages-dev": [
                {"name": "phpunit/phpunit", "version": "9.5.0"}
            ]
        }
        content = json.dumps(composer_lock)
        rule = MatchRule(packages=["symfony/console"], exact_versions=["5.4.0"], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_composer_lock(content, rule, compiled_ranges)
        
        assert any(x["package"] == "symfony/console" and x["version"] == "5.4.0" for x in results)
        assert results[0]["source"] == "composer.lock"
        print("✓ Parse composer.lock with packages")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse composer.lock with packages: {e}")
        tests_failed += 1

    # Test 2: Parse composer.lock with dev packages
    try:
        composer_lock = {
            "packages": [
                {"name": "symfony/console", "version": "5.4.0"}
            ],
            "packages-dev": [
                {"name": "phpunit/phpunit", "version": "9.5.0"}
            ]
        }
        content = json.dumps(composer_lock)
        rule = MatchRule(packages=["phpunit/phpunit"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_composer_lock(content, rule, compiled_ranges)
        
        assert any(r["package"] == "phpunit/phpunit" for r in results)
        print("✓ Parse composer.lock with dev packages")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse composer.lock with dev packages: {e}")
        tests_failed += 1

    # Test 3: Parse composer.lock with short package name
    try:
        composer_lock = {
            "packages": [
                {"name": "vendor/package", "version": "1.0.0"}
            ],
            "packages-dev": []
        }
        content = json.dumps(composer_lock)
        rule = MatchRule(packages=["package"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_composer_lock(content, rule, compiled_ranges)
        
        # Should match because we check both full name and short name
        assert len(results) > 0
        print("✓ Parse composer.lock with short package name")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse composer.lock with short package name: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_gemfile_lock_parser():
    """Test Ruby Gemfile.lock parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    # Test 1: Parse Gemfile.lock with gems
    try:
        gemfile_lock_content = """GEM
  remote: https://rubygems.org/
  specs:
    actioncable (7.0.4)
      actionpack (= 7.0.4)
    actionpack (7.0.4)
      rack (~> 2.0)
    rails (7.0.4)
      actioncable (= 7.0.4)
      actionpack (= 7.0.4)
"""
        rule = MatchRule(packages=["actioncable"], exact_versions=["7.0.4"], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_gemfile_lock(gemfile_lock_content, rule, compiled_ranges)
        
        assert any(x["package"] == "actioncable" and x["version"] == "7.0.4" for x in results)
        assert results[0]["source"] == "Gemfile.lock"
        print("✓ Parse Gemfile.lock with gems")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse Gemfile.lock with gems: {e}")
        tests_failed += 1

    # Test 2: Parse Gemfile.lock with multiple gems
    try:
        gemfile_lock_content = """GEM
  specs:
    rails (7.0.4)
    actionpack (7.0.4)
    bundler (2.3.0)
"""
        rule = MatchRule(packages=["rails", "actionpack"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_gemfile_lock(gemfile_lock_content, rule, compiled_ranges)
        
        assert len(results) >= 2
        print("✓ Parse Gemfile.lock with multiple gems")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse Gemfile.lock with multiple gems: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_gradle_lock_parser():
    """Test Gradle gradle.lock parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    # Test 1: Parse gradle.lock with dependencies
    try:
        gradle_lock_content = """com.google.guava:guava:31.1-jre=31.1-android-jre
com.fasterxml.jackson.core:jackson-databind:2.14.0=2.14.0
org.junit.jupiter:junit-jupiter:5.9.0=5.9.0
"""
        rule = MatchRule(packages=["guava", "jackson-databind"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_gradle_lock(gradle_lock_content, rule, compiled_ranges)
        
        assert any(x["package"] == "guava" for x in results)
        assert any(x["package"] == "jackson-databind" for x in results)
        assert results[0]["source"] == "gradle.lock"
        print("✓ Parse gradle.lock with dependencies")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse gradle.lock with dependencies: {e}")
        tests_failed += 1

    # Test 2: Parse gradle.lock with version matching
    try:
        gradle_lock_content = """com.google.guava:guava:31.1-jre=31.1-android-jre
org.junit.jupiter:junit-jupiter:5.9.0=5.9.0
"""
        rule = MatchRule(packages=["guava"], exact_versions=["31.1-android-jre"], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_gradle_lock(gradle_lock_content, rule, compiled_ranges)
        
        assert any(r["package"] == "guava" and r["version"] == "31.1-android-jre" for r in results)
        print("✓ Parse gradle.lock with version matching")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse gradle.lock with version matching: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_pubspec_lock_parser():
    """Test Dart pubspec.lock parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    if not scanner.HAS_YAML:
        print("⊘ pubspec.lock tests skipped (PyYAML library not installed)")
        return 1, 0

    # Test 1: Parse pubspec.lock with packages
    try:
        import yaml
        pubspec_lock = {
            "http": {"version": "0.13.4"},
            "path": {"version": "1.8.2"},
            "petitparser": {"version": "4.4.0"}
        }
        content = yaml.dump(pubspec_lock)
        rule = MatchRule(packages=["http"], exact_versions=["0.13.4"], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_pubspec_lock(content, rule, compiled_ranges)
        
        assert any(x["package"] == "http" and x["version"] == "0.13.4" for x in results)
        assert results[0]["source"] == "pubspec.lock"
        print("✓ Parse pubspec.lock with packages")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse pubspec.lock with packages: {e}")
        tests_failed += 1

    # Test 2: Parse pubspec.lock with multiple packages
    try:
        import yaml
        pubspec_lock = {
            "http": {"version": "0.13.4"},
            "path": {"version": "1.8.2"},
            "petitparser": {"version": "4.4.0"}
        }
        content = yaml.dump(pubspec_lock)
        rule = MatchRule(packages=["http", "path", "petitparser"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_pubspec_lock(content, rule, compiled_ranges)
        
        assert len(results) == 3
        print("✓ Parse pubspec.lock with multiple packages")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse pubspec.lock with multiple packages: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_requirements_txt_parser():
    """Test pip requirements.txt parser."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")
    utils = importlib.import_module(f"{package_name}.src.utils")
    MatchRule = utils.MatchRule

    tests_passed = 0
    tests_failed = 0

    # Test 1: Parse requirements.txt with basic versions
    try:
        requirements_content = """requests==2.28.1
django==4.1.0
celery>=5.0,<6.0
"""
        rule = MatchRule(packages=["requests", "django"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_requirements_txt(requirements_content, rule, compiled_ranges)
        
        assert len(results) > 0, f"Should find matches, got {len(results)} results"
        assert any(x["package"] == "requests" and x["version"] == "2.28.1" for x in results), f"Should find requests 2.28.1, got {results}"
        assert any(x["package"] == "django" and x["version"] == "4.1.0" for x in results), f"Should find django 4.1.0, got {results}"
        assert results[0]["source"] == "requirements.txt"
        print("✓ Parse requirements.txt with basic versions")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse requirements.txt with basic versions: {e}")
        tests_failed += 1

    # Test 2: Parse requirements.txt with complex constraints
    try:
        requirements_content = """requests>=2.25,<3.0
django~=4.0
numpy==1.21.0
"""
        rule = MatchRule(packages=["requests", "django", "numpy"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_requirements_txt(requirements_content, rule, compiled_ranges)
        
        assert len(results) >= 3
        print("✓ Parse requirements.txt with complex constraints")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse requirements.txt with complex constraints: {e}")
        tests_failed += 1

    # Test 3: Parse requirements.txt with comments
    try:
        requirements_content = """# Production dependencies
requests==2.28.1  # Web requests library
django==4.1.0
# celery==5.2.0  # commented out

# Development dependencies
pytest==7.1.2
"""
        rule = MatchRule(packages=["requests"], exact_versions=[], version_ranges=[])
        compiled_ranges = []
        
        results = scanner.parse_requirements_txt(requirements_content, rule, compiled_ranges)
        
        assert any(r["package"] == "requests" for r in results)
        print("✓ Parse requirements.txt with comments")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Parse requirements.txt with comments: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


def test_format_detection():
    """Test lock file format detection."""
    import importlib
    scanner = importlib.import_module(f"{package_name}.src.scanner")

    tests_passed = 0
    tests_failed = 0

    # Test 1: Detect all formats
    try:
        test_cases = [
            ("/repo/package-lock.json", "package-lock.json"),
            ("/repo/yarn.lock", "yarn.lock"),
            ("/repo/poetry.lock", "poetry.lock"),
            ("/repo/Pipfile.lock", "Pipfile.lock"),
            ("/repo/go.sum", "go.sum"),
            ("/repo/Cargo.lock", "Cargo.lock"),
            ("/repo/composer.lock", "composer.lock"),
            ("/repo/Gemfile.lock", "Gemfile.lock"),
            ("/repo/gradle.lock", "gradle.lock"),
            ("/repo/pubspec.lock", "pubspec.lock"),
            ("/repo/requirements.txt", "requirements.txt"),
            ("/repo/requirements.lock", "requirements.txt"),
        ]
        
        for file_path, expected in test_cases:
            result = scanner.get_lock_file_format(file_path)
            assert result == expected, f"Expected {expected} for {file_path}, got {result}"
        
        print("✓ Detect all lock file formats")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Detect all lock file formats: {e}")
        tests_failed += 1

    # Test 2: Unknown format returns None
    try:
        result = scanner.get_lock_file_format("/repo/unknown.txt")
        assert result is None
        result = scanner.get_lock_file_format("/repo/Makefile")
        assert result is None
        print("✓ Unknown format returns None")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Unknown format returns None: {e}")
        tests_failed += 1

    # Test 3: should_parse_as_package_lock function
    try:
        assert scanner.should_parse_as_package_lock("package-lock.json") is True
        assert scanner.should_parse_as_package_lock("poetry.lock") is True
        assert scanner.should_parse_as_package_lock("unknown.txt") is False
        print("✓ should_parse_as_package_lock function")
        tests_passed += 1
    except Exception as e:
        print(f"❌ should_parse_as_package_lock function: {e}")
        tests_failed += 1

    return tests_passed, tests_failed


if __name__ == "__main__":
    print("Testing Lock File Format Parsers")
    print("=" * 70)

    all_passed = 0
    all_failed = 0

    print("\nTesting Pipenv Pipfile.lock Parser...")
    print("-" * 70)
    passed, failed = test_pipfile_lock_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting Poetry poetry.lock Parser...")
    print("-" * 70)
    passed, failed = test_poetry_lock_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting Go go.sum Parser...")
    print("-" * 70)
    passed, failed = test_go_sum_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting Rust Cargo.lock Parser...")
    print("-" * 70)
    passed, failed = test_cargo_lock_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting PHP composer.lock Parser...")
    print("-" * 70)
    passed, failed = test_composer_lock_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting Ruby Gemfile.lock Parser...")
    print("-" * 70)
    passed, failed = test_gemfile_lock_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting Gradle gradle.lock Parser...")
    print("-" * 70)
    passed, failed = test_gradle_lock_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting Dart pubspec.lock Parser...")
    print("-" * 70)
    passed, failed = test_pubspec_lock_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting pip requirements.txt Parser...")
    print("-" * 70)
    passed, failed = test_requirements_txt_parser()
    all_passed += passed
    all_failed += failed

    print("\nTesting Lock File Format Detection...")
    print("-" * 70)
    passed, failed = test_format_detection()
    all_passed += passed
    all_failed += failed

    print("\n" + "=" * 70)
    print(f"Total Results: {all_passed} passed, {all_failed} failed")
    print("=" * 70)

    sys.exit(0 if all_failed == 0 else 1)
