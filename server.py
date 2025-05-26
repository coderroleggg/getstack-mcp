from mcp.server.fastmcp import FastMCP
import os
import logging
import requests
import json
import tempfile
import shutil
from typing import Dict, Any, List
from git import Repo
from pathlib import Path

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# MCP initialization
mcp = FastMCP(
    name="GetStack Templates MCP",
    description="MCP for managing getstack templates. Provides functions for listing and using templates from GitHub repository.",
    version="1.0.0",
    author="Oleg Stefanov",
)

# Constants
GITHUB_REPO_OWNER = "coderroleggg"
GITHUB_REPO_NAME = "getstack-templates"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}.git"


@mcp.tool("get_templates")
def get_templates() -> Dict[str, Any]:
    """
    Gets the list of available templates from the GitHub repository.
    
    Returns:
    - List of template names (folders in the repository root)
    """
    try:
        # Use GitHub API to get repository contents
        response = requests.get(f"{GITHUB_API_URL}/contents/")
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"Failed to fetch repository contents. Status code: {response.status_code}"
            }
        
        contents = response.json()
        
        # Filter only directories
        templates = []
        for item in contents:
            if item.get("type") == "dir":
                templates.append({
                    "name": item["name"],
                    "path": item["path"],
                    "url": item["html_url"]
                })
        
        return {
            "success": True,
            "templates": templates,
            "count": len(templates)
        }
        
    except requests.RequestException as e:
        logger.error(f"Error fetching templates: {e}")
        return {
            "success": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool("use_template")
def use_template(template_name: str, current_folder: str) -> Dict[str, Any]:
    """
    Clones a specific template from the repository to the specified folder.
    
    Parameters:
    - template_name: Name of the template to use (folder name in the repository)
    - current_folder: Target folder where to copy the template (full absolute path)
    
    Returns:
    - Operation status and copied files information
    """
    try:
        # Validate inputs
        if not template_name:
            return {
                "success": False,
                "error": "Template name is required"
            }
        
        if not current_folder:
            return {
                "success": False,
                "error": "Target folder is required"
            }
        
        # Expand the path and make it absolute
        target_path = Path(current_folder).expanduser().absolute()
        
        # Create target directory if it doesn't exist
        target_path.mkdir(parents=True, exist_ok=True)
        
        # First, check if the template exists
        response = requests.get(f"{GITHUB_API_URL}/contents/{template_name}")
        
        if response.status_code == 404:
            return {
                "success": False,
                "error": f"Template '{template_name}' not found in the repository"
            }
        elif response.status_code != 200:
            return {
                "success": False,
                "error": f"Failed to check template. Status code: {response.status_code}"
            }
        
        # Create a temporary directory for cloning
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            logger.info(f"Cloning repository to temporary directory: {temp_path}")
            
            # Clone the repository
            repo = Repo.clone_from(
                GITHUB_REPO_URL,
                temp_path,
                depth=1  # Shallow clone for faster operation
            )
            
            # Path to the template in the cloned repo
            template_path = temp_path / template_name
            
            if not template_path.exists() or not template_path.is_dir():
                return {
                    "success": False,
                    "error": f"Template '{template_name}' not found in the cloned repository"
                }
            
            # Copy template files to the target directory
            copied_files = []
            for item in template_path.rglob("*"):
                if item.is_file():
                    # Calculate relative path from template root
                    relative_path = item.relative_to(template_path)
                    
                    # Target file path
                    target_file = target_path / relative_path
                    
                    # Create parent directories if needed
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy the file
                    shutil.copy2(item, target_file)
                    copied_files.append(str(relative_path))
            
            logger.info(f"Successfully copied {len(copied_files)} files to {target_path}")
            
            return {
                "success": True,
                "template_name": template_name,
                "target_folder": str(target_path),
                "files_copied": len(copied_files),
                "files": copied_files
            }
        
    except Exception as e:
        logger.error(f"Error using template: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def main():
    # Run MCP server
    mcp.run()


if __name__ == "__main__":
    main()
