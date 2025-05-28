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
    description="MCP for managing getstack templates from Supabase database with RAG search. Provides functions for listing, searching and using templates stored in Supabase with vector embeddings.",
    version="2.1.2",
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
    - List of templates sorted by relevance with similarity scores
    """
    similarity_threshold = 0
    try:
        if not query.strip():
            return {
                "success": False,
                "error": "Search query cannot be empty"
            }
        
        # Generate embedding for search query via API frontend
        try:
            query_embedding = _generate_embedding_via_api(query)
        except Exception as e:
            # If embedding generation fails, perform keyword search
            logger.warning(f"Failed to generate embedding, falling back to keyword search: {e}")
            return _fallback_keyword_search(query, limit)
        
        # Perform vector search in Supabase
        # Use RPC function for similarity search
        response = supabase.rpc(
            "search_templates_by_similarity",
            {
                "query_embedding": query_embedding,
                "similarity_threshold": similarity_threshold,
                "match_count": limit
            }
        ).execute()
        
        if not response.data:
            return {
                "success": True,
                "templates": [],
                "count": 0,
                "message": f"No templates found matching query '{query}' with similarity >= {similarity_threshold}",
                "search_type": "rag"
            }
        
        # Format results
        templates = []
        for template in response.data:
            readme_preview = ""
            if template.get("readme_content"):
                readme_preview = template["readme_content"][:200]
                if len(template["readme_content"]) > 200:
                    readme_preview += "..."
            
            templates.append({
                "id": template["id"],
                "repo_name": template["repo_name"],
                "repo_owner": template["repo_owner"],
                "repo_url": template["repo_url"],
                "readme_preview": readme_preview,
                "similarity": round(template.get("similarity", 0), 3),
                "created_at": template["created_at"]
            })
        
        return {
            "success": True,
            "templates": templates,
            "count": len(templates),
            "query": query,
            "similarity_threshold": similarity_threshold,
            "search_type": "rag"
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
    - Operation status and copied files information
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
                "total_files": len(copied_files)
            }
        
    except Exception as e:
        logger.error(f"Error using template: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def _generate_embedding_via_api(text: str) -> List[float]:
    """
    Generates embedding for text using API endpoint frontend.
    
    Args:
        text: Text to generate embedding for
        
    Returns:
        List of numbers representing embedding
        
    Raises:
        ValueError: If API is not available or returns error
    """
    try:
        headers = {
            "Content-Type": "application/json"
        }
        
        # Send request to API endpoint frontend
        response = requests.post(
            f"{FRONTEND_API_URL}/api/embeddings",
            json={"text": text},
            headers=headers,
            timeout=30  # 30 seconds timeout
        )
        
        if response.status_code == 401:
            raise ValueError("Authentication required. Please provide valid auth token.")
        elif response.status_code == 503:
            raise ValueError("OpenAI API not configured on frontend server")
        elif response.status_code != 200:
            error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
            error_message = error_data.get('error', f'HTTP {response.status_code}')
            raise ValueError(f"Frontend API error: {error_message}")
        
        data = response.json()
        return data["embedding"]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error when calling frontend API: {e}")
        raise ValueError(f"Failed to connect to frontend API: {str(e)}")
    except Exception as e:
        logger.error(f"Error generating embedding via API: {e}")
        raise ValueError(f"Embedding generation failed: {str(e)}")


def _fallback_keyword_search(query: str, limit: int) -> Dict[str, Any]:
    """
    Performs keyword search as fallback when RAG search is unavailable.
    
    Args:
        query: Search query
        limit: Maximum number of results
        
    Returns:
        Results of keyword search
    """
    try:
        search_term = query.strip()
        
        # Perform keyword search in repo_name, repo_owner and readme_content
        response = supabase.table("templates").select("*").or_(
            f"repo_name.ilike.%{search_term}%,"
            f"repo_owner.ilike.%{search_term}%,"
            f"readme_content.ilike.%{search_term}%"
        ).order("created_at", desc=True).limit(limit).execute()
        
        if not response.data:
            return {
                "success": True,
                "templates": [],
                "count": 0,
                "message": f"No templates found matching keyword '{query}'",
                "search_type": "keyword"
            }
        
        # Format results
        templates = []
        for template in response.data:
            readme_preview = ""
            if template.get("readme_content"):
                readme_preview = template["readme_content"][:200]
                if len(template["readme_content"]) > 200:
                    readme_preview += "..."
            
            templates.append({
                "id": template["id"],
                "repo_name": template["repo_name"],
                "repo_owner": template["repo_owner"],
                "repo_url": template["repo_url"],
                "readme_preview": readme_preview,
                "similarity": 0.5,  # Fixed value for keyword search
                "created_at": template["created_at"]
            })
        
        return {
            "success": True,
            "templates": templates,
            "count": len(templates),
            "query": query,
            "search_type": "keyword",
            "message": "Keyword search results (AI search unavailable)"
        }
        
    except Exception as e:
        logger.error(f"Error in fallback keyword search: {e}")
        return {
            "success": False,
            "error": f"Keyword search error: {str(e)}"
        }


def main():
    # Run MCP server
    mcp.run()


if __name__ == "__main__":
    main()
