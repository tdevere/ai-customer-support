"""
Basic structure tests to validate the codebase organization.
"""

import os
import pytest
from pathlib import Path


def test_project_structure():
    """Test that all required directories exist."""
    base_dir = Path(__file__).parent.parent

    required_dirs = [
        "agents",
        "orchestrator",
        "integrations",
        "shared",
        "tests",
        "infra",
        ".github/workflows",
    ]

    for dir_name in required_dirs:
        dir_path = base_dir / dir_name
        assert dir_path.exists(), f"Required directory {dir_name} not found"
        assert dir_path.is_dir(), f"{dir_name} is not a directory"


def test_agent_files_exist():
    """Test that all agent files exist."""
    base_dir = Path(__file__).parent.parent / "agents"

    required_files = [
        "__init__.py",
        "billing_agent.py",
        "tech_agent.py",
        "returns_agent.py",
        "registry.yaml",
    ]

    for file_name in required_files:
        file_path = base_dir / file_name
        assert file_path.exists(), f"Required file {file_name} not found in agents/"
        assert file_path.is_file(), f"{file_name} is not a file"


def test_orchestrator_files_exist():
    """Test that orchestrator files exist."""
    base_dir = Path(__file__).parent.parent / "orchestrator"

    required_files = [
        "__init__.py",
        "graph.py",
        "supervisor.py",
        "verifier.py",
        "escalator.py",
        "custom_answers.py",
    ]

    for file_name in required_files:
        file_path = base_dir / file_name
        assert (
            file_path.exists()
        ), f"Required file {file_name} not found in orchestrator/"


def test_integration_files_exist():
    """Test that integration files exist."""
    base_dir = Path(__file__).parent.parent / "integrations"

    required_files = ["__init__.py", "intercom.py", "conversations.py"]

    for file_name in required_files:
        file_path = base_dir / file_name
        assert (
            file_path.exists()
        ), f"Required file {file_name} not found in integrations/"

    # Check tools directory
    tools_dir = base_dir / "tools"
    assert tools_dir.exists()
    assert (tools_dir / "stripe_tools.py").exists()
    assert (tools_dir / "jira_tools.py").exists()
    assert (tools_dir / "shopify_tools.py").exists()


def test_shared_files_exist():
    """Test that shared files exist."""
    base_dir = Path(__file__).parent.parent / "shared"

    required_files = ["__init__.py", "config.py", "memory.py", "rag.py"]

    for file_name in required_files:
        file_path = base_dir / file_name
        assert file_path.exists(), f"Required file {file_name} not found in shared/"


def test_config_files_exist():
    """Test that configuration files exist."""
    base_dir = Path(__file__).parent.parent

    required_files = [
        "requirements.txt",
        ".gitignore",
        "README.md",
        "function_app.py",
        "host.json",
        ".funcignore",
    ]

    for file_name in required_files:
        file_path = base_dir / file_name
        assert file_path.exists(), f"Required file {file_name} not found"


def test_infrastructure_files_exist():
    """Test that infrastructure files exist."""
    base_dir = Path(__file__).parent.parent / "infra"

    assert (base_dir / "main.tf").exists()
    assert (base_dir / "README.md").exists()


def test_cicd_workflow_exists():
    """Test that CI/CD workflow exists."""
    workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "ci-cd.yml"
    assert workflow_path.exists()


def test_documentation_exists():
    """Test that documentation files exist."""
    docs_dir = Path(__file__).parent.parent / "docs"

    assert docs_dir.exists()
    assert (docs_dir / "DEPLOYMENT.md").exists()
    assert (docs_dir / "ARCHITECTURE.md").exists()


def test_requirements_has_content():
    """Test that requirements.txt has content."""
    req_file = Path(__file__).parent.parent / "requirements.txt"
    content = req_file.read_text()

    # Check for key dependencies
    assert "langgraph" in content.lower()
    assert "langchain" in content.lower()
    assert "azure" in content.lower()
    assert "fastapi" in content.lower()


def test_registry_yaml_valid():
    """Test that registry.yaml exists and has content."""
    registry_file = Path(__file__).parent.parent / "agents" / "registry.yaml"
    content = registry_file.read_text()

    # Check for agent registrations
    assert "billing" in content
    assert "technical" in content
    assert "returns" in content


def test_custom_answers_yaml_valid():
    """Test that custom_answers.yaml exists and has valid entries."""
    ca_file = Path(__file__).parent.parent / "agents" / "custom_answers.yaml"
    assert ca_file.exists(), "agents/custom_answers.yaml not found"
    content = ca_file.read_text()
    assert "custom_answers" in content
    assert "patterns" in content
    assert "answer" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
