from mcp.server.fastmcp import FastMCP
import os
import logging
import requests
import tempfile
import shutil
from typing import Dict, Any, List, Optional
from git import Repo
from pathlib import Path
from supabase import create_client, Client

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# MCP initialization
mcp = FastMCP(
    name="GetStack Templates MCP",
    description="MCP for managing getstack templates. Provides secure template search via frontend API (with server-side embedding generation) and direct template cloning from repository sources. Includes popularity metrics like likes and dislikes.",
    version="2.3.0",
    author="Oleg Stefanov",
)

# Supabase configuration
SUPABASE_URL = "https://vgsfomxzqyxtwlgxrruu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnc2ZvbXh6cXl4dHdsZ3hycnV1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgyNzQ5MzYsImV4cCI6MjA2Mzg1MDkzNn0.3bE-DI3_Hbg9gtCS-9SAV4N-4ELtRQCgCOmWaXhB2oI"
# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Frontend API configuration
FRONTEND_API_URL = os.getenv("FRONTEND_API_URL", "https://getstack.coderr.online")

@mcp.tool("search_templates")
def search_templates(
    query: str, 
    limit: int = 10
) -> Dict[str, Any]:
    """
    Performs RAG search of templates based on vector similarity with README content.
    
    Parameters:
    - query: Search query to find relevant templates
    - limit: Maximum number of results (default 10)
    
    Returns:
    - List of templates sorted by relevance with similarity scores, likes and dislikes counts
    """
    try:
        if not query.strip():
            return {
                "success": False,
                "error": "Search query cannot be empty"
            }
        
        try:
            response = requests.get(
                f"{FRONTEND_API_URL}/api/templates",
                params={"search": query.strip()},
                timeout=30
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Frontend API error: HTTP {response.status_code}"
                }
            
            data = response.json()
            templates_data = data.get("templates", [])
            search_type = data.get("searchType", "unknown")
            message = data.get("message", "")
            
            # Limit results
            limited_templates = templates_data[:limit]
            
            # Format results for MCP response
            templates = []
            for template in limited_templates:
                readme_preview = ""
                if template.get("readme_content"):
                    readme_preview = template["readme_content"][:200]
                    if len(template["readme_content"]) > 200:
                        readme_preview += "..."
                
                templates.append({
                    "id": template["id"],
                    "repo_name": template["repo_name"],
                    "readme_preview": readme_preview,
                    "similarity": template.get("similarity", 0),
                    "created_at": template["created_at"],
                    "likes_count": template.get("likes_count", 0),
                    "dislikes_count": template.get("dislikes_count", 0)
                })
            
            return {
                "success": True,
                "templates": templates,
                "count": len(templates),
                "query": query,
                "search_type": search_type,
                "message": message
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error when calling frontend API: {e}")
            return {
                "success": False,
                "error": f"Failed to connect to frontend API: {str(e)}"
            }
        
    except Exception as e:
        logger.error(f"Error searching templates: {e}")
        return {
            "success": False,
            "error": f"Search error: {str(e)}"
        }


@mcp.tool("use_template")
def use_template(template_id: str, current_folder: str) -> Dict[str, Any]:
    """
    Clones a specific template repository from Supabase to the specified folder.
    
    Parameters:
    - template_id: ID of the template in Supabase database
    - current_folder: Target folder where to copy the template (full absolute path)
    
    Returns:
    - Operation status, copied files information, and template popularity metrics (likes/dislikes)
    """
    try:
        # Validate inputs
        if not template_id:
            return {
                "success": False,
                "error": "Template ID is required"
            }
        
        if not current_folder:
            return {
                "success": False,
                "error": "Target folder is required"
            }
        
        # Get template from Supabase
        response = supabase.table("templates").select("*").eq("id", template_id).execute()
        
        if not response.data:
            return {
                "success": False,
                "error": f"Template with ID '{template_id}' not found in database"
            }
        
        template = response.data[0]
        repo_url = template["repo_url"]
        repo_name = template["repo_name"]
        repo_owner = template["repo_owner"]
        
        # Expand the path and make it absolute
        target_path = Path(current_folder).expanduser().absolute()
        
        # Create target directory if it doesn't exist
        target_path.mkdir(parents=True, exist_ok=True)
        
        # Check if repository is accessible
        github_api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        github_response = requests.get(github_api_url)
        
        if github_response.status_code == 404:
            return {
                "success": False,
                "error": f"Repository '{repo_owner}/{repo_name}' not found or is private"
            }
        elif github_response.status_code != 200:
            return {
                "success": False,
                "error": f"Failed to access repository. Status code: {github_response.status_code}"
            }
        
        # Create a temporary directory for cloning
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            logger.info(f"Cloning repository {repo_url} to temporary directory: {temp_path}")
            
            # Clone the repository
            try:
                repo = Repo.clone_from(
                    repo_url,
                    temp_path,
                    depth=1  # Shallow clone for faster operation
                )
            except Exception as clone_error:
                return {
                    "success": False,
                    "error": f"Failed to clone repository: {str(clone_error)}"
                }
            
            # Copy all files from the cloned repo to the target directory
            copied_files = []
            for item in temp_path.rglob("*"):
                if item.is_file() and not item.name.startswith('.git'):
                    # Calculate relative path from repo root
                    relative_path = item.relative_to(temp_path)
                    
                    # Skip .git directory and its contents
                    if '.git' in relative_path.parts:
                        continue
                    
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
                "template_id": template_id,
                "template_name": repo_name,
                "repo_url": repo_url,
                "target_folder": str(target_path),
                "files_copied": len(copied_files),
                "files": copied_files[:20] if len(copied_files) > 20 else copied_files,  # Limit output for readability
                "total_files": len(copied_files),
                "likes_count": template.get("likes_count", 0),
                "dislikes_count": template.get("dislikes_count", 0)
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
