"""
Microsoft Docs MCP Integration Service
Provides real-time grounding with official Microsoft documentation
"""
import logging
import os
from typing import List, Dict, Optional
import httpx
import json

logger = logging.getLogger(__name__)

class MicrosoftDocsService:
    """Service for integrating with Microsoft Docs MCP Server"""
    
    def __init__(self):
        self.dapr_port = os.getenv("DAPR_HTTP_PORT", "3500")
        self.dapr_service_id = os.getenv("DAPR_SERVICE_ID", "mcp-service")
        self.mcp_base_url = f"http://localhost:{self.dapr_port}/v1.0/invoke/{self.dapr_service_id}/method"
        self.timeout = int(os.getenv("MCP_HTTP_TIMEOUT", "60"))
        self.max_results = 5  # Limit results for prompt efficiency
    
    async def search_azure_docs(self, query: str, max_results: Optional[int] = None) -> List[Dict]:
        """
        Search Microsoft Azure documentation for relevant content
        
        Args:
            query: Search query for Azure documentation
            max_results: Maximum number of results to return (default: 5)
            
        Returns:
            List of document excerpts with title, content, and URL
        """
        if max_results is None:
            max_results = self.max_results
            
        try:
            # Try direct MCP integration first
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Call Microsoft Docs MCP Server through Dapr
                response = await client.post(
                    f"{self.mcp_base_url}/mcp/call_tool",
                    json={
                        "tool": "microsoft_docs_search",
                        "arguments": {
                            "query": query
                        }
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Extract and limit results
                    if isinstance(result, dict) and "content" in result:
                        docs = result["content"]
                        if isinstance(docs, list):
                            # Limit results and ensure they're relevant
                            limited_docs = docs[:max_results]
                            logger.info(f"Found {len(limited_docs)} Azure docs for query: {query[:50]}...")
                            return limited_docs
                    
                    logger.warning(f"Unexpected Microsoft Docs MCP response format: {result}")
                
        except Exception as e:
            logger.warning(f"MCP service unavailable, using fallback: {e}")
        
        # Fallback: Use curated Azure documentation snippets
        return self._get_fallback_docs(query, max_results)
    
    def _get_fallback_docs(self, query: str, max_results: int) -> List[Dict]:
        """
        Fallback method with curated Azure documentation snippets
        """
        # Curated Azure documentation knowledge base
        azure_docs_kb = {
            "multi-region": [
                {
                    "title": "Azure Multi-Region Deployment Patterns",
                    "content": "Implement active-active or active-passive configurations across Azure regions. Use Azure Front Door for global load balancing and automatic failover. Configure cross-region database replication with Azure SQL geo-replication or Cosmos DB multi-region writes.",
                    "contentUrl": "https://learn.microsoft.com/en-us/azure/architecture/guide/design-principles/redundancy"
                },
                {
                    "title": "Azure Paired Regions for Disaster Recovery",
                    "content": "Each Azure region is paired with another region within the same geography. Paired regions provide automatic failover for platform services and coordinated updates. Design your DR strategy using paired regions for optimal recovery capabilities.",
                    "contentUrl": "https://learn.microsoft.com/en-us/azure/reliability/cross-region-replication-azure"
                }
            ],
            "cost-optimization": [
                {
                    "title": "Azure Reserved Instances and Savings Plans",
                    "content": "Save up to 72% with Azure Reserved Instances for compute resources. Use Azure Savings Plans for flexible cost optimization across compute services. Combine with Azure Hybrid Benefit for Windows Server and SQL Server licensing cost reductions.",
                    "contentUrl": "https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/save-compute-costs-reservations"
                },
                {
                    "title": "Azure Pricing Calculator and Cost Management",
                    "content": "Use the Azure Pricing Calculator to estimate costs before deployment. Set up budgets and alerts in Azure Cost Management. Monitor usage patterns and optimize resource allocation.",
                    "contentUrl": "https://learn.microsoft.com/en-us/azure/cost-management-billing/"
                }
            ],
            "high-availability": [
                {
                    "title": "Azure High Availability Architecture",
                    "content": "Design for 99.99% availability using Azure availability sets, zones, and regions. Implement health probes, auto-scaling, and failover mechanisms. Use Azure Load Balancer and Application Gateway for distribution.",
                    "contentUrl": "https://learn.microsoft.com/en-us/azure/architecture/guide/design-principles/redundancy"
                }
            ],
            "security": [
                {
                    "title": "Azure Security Best Practices",
                    "content": "Implement defense in depth with Azure Security Center, Key Vault for secrets management, and network security groups. Use Azure Active Directory for identity management and implement Zero Trust principles.",
                    "contentUrl": "https://learn.microsoft.com/en-us/azure/security/fundamentals/best-practices-and-patterns"
                }
            ]
        }
        
        # Search for relevant docs based on query keywords
        query_lower = query.lower()
        relevant_docs = []
        
        for category, docs in azure_docs_kb.items():
            if any(keyword in query_lower for keyword in category.split('-')):
                relevant_docs.extend(docs)
        
        # If no specific matches, return general architecture guidance
        if not relevant_docs:
            relevant_docs = azure_docs_kb.get("high-availability", [])
        
        # Limit results
        return relevant_docs[:max_results]
    
    async def get_architecture_guidance(self, architecture_type: str, requirements: List[str]) -> Dict:
        """
        Get comprehensive Azure architecture guidance for specific requirements
        
        Args:
            architecture_type: Type of architecture (e.g., "e-commerce", "saas", "enterprise")
            requirements: List of specific requirements (e.g., ["multi-region", "high-availability", "cost-optimization"])
            
        Returns:
            Dictionary containing categorized guidance from official docs
        """
        guidance = {
            "architecture_patterns": [],
            "best_practices": [],
            "cost_optimization": [],
            "security_guidance": [],
            "resilience_strategies": [],
            "multi_region_guidance": []
        }
        
        # Search queries for comprehensive guidance
        search_queries = [
            f"Azure {architecture_type} architecture best practices",
            f"Azure {architecture_type} multi-region deployment",
            f"Azure {architecture_type} cost optimization",
            f"Azure {architecture_type} security guidelines",
            f"Azure {architecture_type} high availability disaster recovery",
            "Azure Well-Architected Framework reliability",
            "Azure availability zones regions",
            "Azure cost management optimization"
        ]
        
        # Add requirement-specific queries
        for requirement in requirements:
            if requirement.lower() in ["multi-region", "resilience", "disaster-recovery"]:
                search_queries.append(f"Azure multi-region {requirement} best practices")
            elif requirement.lower() in ["cost", "pricing", "optimization"]:
                search_queries.append(f"Azure cost optimization {architecture_type}")
            elif requirement.lower() in ["security", "compliance"]:
                search_queries.append(f"Azure security {architecture_type} compliance")
        
        # Execute searches and categorize results
        for query in search_queries[:8]:  # Limit to avoid too many API calls
            try:
                docs = await self.search_azure_docs(query, max_results=2)
                
                # Categorize based on query content
                if "cost" in query.lower() or "optimization" in query.lower():
                    guidance["cost_optimization"].extend(docs)
                elif "security" in query.lower() or "compliance" in query.lower():
                    guidance["security_guidance"].extend(docs)
                elif "multi-region" in query.lower() or "availability" in query.lower():
                    guidance["multi_region_guidance"].extend(docs)
                elif "resilience" in query.lower() or "disaster" in query.lower():
                    guidance["resilience_strategies"].extend(docs)
                elif "best practices" in query.lower():
                    guidance["best_practices"].extend(docs)
                else:
                    guidance["architecture_patterns"].extend(docs)
                    
            except Exception as e:
                logger.error(f"Error in architecture guidance search for '{query}': {e}")
                continue
        
        # Remove duplicates while preserving order
        for category in guidance:
            seen_urls = set()
            unique_docs = []
            for doc in guidance[category]:
                if isinstance(doc, dict):
                    url = doc.get("contentUrl", "")
                    if url not in seen_urls:
                        seen_urls.add(url)
                        unique_docs.append(doc)
            guidance[category] = unique_docs
        
        return guidance
    
    async def get_service_guidance(self, service_names: List[str]) -> Dict:
        """
        Get specific guidance for Azure services
        
        Args:
            service_names: List of Azure service names
            
        Returns:
            Dictionary mapping service names to their documentation
        """
        service_docs = {}
        
        for service in service_names[:10]:  # Limit services to avoid too many calls
            try:
                docs = await self.search_azure_docs(
                    f"Azure {service} best practices configuration", 
                    max_results=2
                )
                if docs:
                    service_docs[service] = docs
            except Exception as e:
                logger.error(f"Error getting guidance for service '{service}': {e}")
                continue
        
        return service_docs
    
    def format_docs_for_prompt(self, docs: List[Dict], category: str = "") -> str:
        """
        Format documentation excerpts for inclusion in AI prompts
        
        Args:
            docs: List of document excerpts
            category: Category name for the docs
            
        Returns:
            Formatted string suitable for AI prompts
        """
        if not docs:
            return ""
        
        formatted = f"\n**{category.title()} (Official Microsoft Documentation):**\n" if category else "\n**Official Microsoft Documentation:**\n"
        
        for i, doc in enumerate(docs[:3], 1):  # Limit to 3 most relevant docs
            if isinstance(doc, dict):
                title = doc.get("title", "Unknown")
                content = doc.get("content", "")
                url = doc.get("contentUrl", "")
                
                # Truncate content to avoid prompt bloat
                if len(content) > 500:
                    content = content[:497] + "..."
                
                formatted += f"\n{i}. **{title}**\n"
                formatted += f"   {content}\n"
                if url:
                    formatted += f"   Reference: {url}\n"
        
        return formatted

# Global service instance
microsoft_docs_service = MicrosoftDocsService()