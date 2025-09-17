"""
Centralized Azure credential management for Container Apps with managed identity and API key support
"""
import os
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.core.credentials import AzureKeyCredential
import logging

logger = logging.getLogger(__name__)

def get_azure_credential():
    """
    Get Azure credential with support for managed identity (for other Azure services)
    
    Returns:
        Azure credential instance configured for the current environment
    """
    # Check if we have a user-assigned managed identity client ID
    managed_identity_client_id = os.getenv("AZURE_CLIENT_ID") or os.getenv("MANAGED_IDENTITY_CLIENT_ID")
    
    if managed_identity_client_id:
        logger.info(f"Using ManagedIdentityCredential with client_id: {managed_identity_client_id[:8]}...")
        try:
            # For user-assigned managed identity in Container Apps
            return ManagedIdentityCredential(client_id=managed_identity_client_id)
        except Exception as e:
            logger.warning(f"ManagedIdentityCredential failed: {e}, falling back to DefaultAzureCredential")
    
    # Fallback to DefaultAzureCredential with managed identity client ID if available
    if managed_identity_client_id:
        logger.info("Using DefaultAzureCredential with managed_identity_client_id")
        try:
            return DefaultAzureCredential(managed_identity_client_id=managed_identity_client_id)
        except Exception as e:
            logger.warning(f"DefaultAzureCredential with client_id failed: {e}, using basic DefaultAzureCredential")
    
    # Final fallback - basic DefaultAzureCredential
    logger.info("Using basic DefaultAzureCredential")
    return DefaultAzureCredential()

def get_credential_for_azure_openai_direct():
    """
    Get credential for direct Azure OpenAI API calls - supports both API key and managed identity
    
    Returns:
        Credential for direct Azure OpenAI Client (supports both patterns)
    """
    # Check for API key first (easier deployment option)
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key and api_key != "placeholder-update-after-deployment":
        logger.info("Using API key authentication for direct Azure OpenAI")
        return AzureKeyCredential(api_key)
    
    # Fall back to managed identity
    logger.info("Using managed identity for direct Azure OpenAI")
    return get_azure_credential()

def get_credential_for_azure_ai_projects():
    """
    Get credential specifically for Azure AI Projects
    
    Since Azure AI Projects SDK doesn't support API key authentication,
    we return None to signal that the REST API approach should be used instead.
    
    Returns:
        None for API key auth (use REST API), or TokenCredential for managed identity
    """
    use_managed_identity = os.getenv("AZURE_AI_USE_MANAGED_IDENTITY", "false").lower() == "true"
    
    if use_managed_identity:
        # For deployed Container Apps - use managed identity with SDK
        logger.info("Using managed identity for Azure AI Projects")
        return get_azure_credential()
    else:
        # For API key authentication - return None to signal REST API usage
        logger.info("Using API key authentication for Azure AI Projects (REST API mode)")
        
        # Validate that we have the required configuration
        project_endpoint = os.getenv("PROJECT_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        
        if not project_endpoint:
            raise ValueError("PROJECT_ENDPOINT not configured. Please provide your Azure AI Foundry project endpoint.")
        
        if not api_key or api_key == "placeholder-update-after-deployment":
            raise ValueError("AZURE_OPENAI_API_KEY not configured. Please provide your Azure OpenAI API key.")
        
        # Return None to signal that REST API should be used
        return None

def get_azure_ai_projects_client():
    """
    Get Azure AI Projects client - automatically chooses between SDK and REST API
    
    Returns:
        Client instance (either SDK-based or REST API-based)
    """
    from .azure_ai_projects_rest_client import create_ai_projects_client
    
    project_endpoint = os.getenv("PROJECT_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    use_managed_identity = os.getenv("AZURE_AI_USE_MANAGED_IDENTITY", "false").lower() == "true"
    
    if not project_endpoint:
        raise ValueError("PROJECT_ENDPOINT not configured")
    
    if use_managed_identity:
        # Use SDK with managed identity
        logger.info("Creating Azure AI Projects client with managed identity")
        try:
            from azure.ai.projects import AIProjectClient
            credential = get_azure_credential()
            return AIProjectClient(endpoint=project_endpoint, credential=credential)
        except Exception as e:
            logger.error(f"Failed to create SDK client with managed identity: {e}")
            raise
    else:
        # Use REST API with API key
        if not api_key or api_key == "placeholder-update-after-deployment":
            raise ValueError("AZURE_OPENAI_API_KEY not configured for API key authentication")
        
        logger.info("Creating Azure AI Projects client with REST API (API key)")
        return create_ai_projects_client(project_endpoint, api_key)

def get_credential_for_scope(scope: str = None):
    """
    Get credential and ensure it works for the specified scope
    
    Args:
        scope: Azure scope to test (optional)
    
    Returns:
        Working Azure credential
    """
    credential = get_azure_credential()
    
    # Test the credential if scope is provided
    if scope:
        try:
            token = credential.get_token(scope)
            logger.info(f"Credential successfully obtained token for scope: {scope}")
            return credential
        except Exception as e:
            logger.error(f"Credential failed for scope {scope}: {e}")
            # Return credential anyway - let the calling service handle the error
            return credential
    
    return credential
