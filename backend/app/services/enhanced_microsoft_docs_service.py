"""
Enhanced Microsoft Docs RAG Service with Azure AI Search Integration
Implements hybrid search combining MCP live results with semantic embeddings
"""
import asyncio
import logging
import os
from typing import List, Dict, Optional, Tuple
import httpx
import json
import numpy as np
from dataclasses import dataclass
from datetime import datetime

# Azure AI Search imports
try:
    from azure.search.documents import SearchClient
    from azure.search.documents.models import VectorizedQuery
    from azure.core.credentials import AzureKeyCredential
    AZURE_SEARCH_AVAILABLE = True
except ImportError:
    AZURE_SEARCH_AVAILABLE = False
    SearchClient = None

# Azure OpenAI imports (using standard openai package with Azure endpoint)
try:
    from openai import AsyncAzureOpenAI
    AZURE_OPENAI_AVAILABLE = True
except ImportError:
    AZURE_OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class DocResult:
    """Structured document result with scoring"""
    title: str
    content: str
    url: str
    category: str
    relevance_score: float
    source: str  # 'mcp' or 'semantic' or 'hybrid'

class EnhancedMicrosoftDocsService:
    """Enhanced Microsoft Docs service with hybrid RAG capabilities"""
    
    def __init__(self):
        # Existing MCP integration
        self.dapr_port = os.getenv("DAPR_HTTP_PORT", "3500")
        self.dapr_service_id = os.getenv("DAPR_SERVICE_ID", "mcp-service")
        self.mcp_base_url = f"http://localhost:{self.dapr_port}/v1.0/invoke/{self.dapr_service_id}/method"
        self.timeout = int(os.getenv("MCP_HTTP_TIMEOUT", "60"))
        
        # Azure AI Search configuration
        self.search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.search_key = os.getenv("AZURE_SEARCH_KEY")
        self.search_index = os.getenv("AZURE_SEARCH_INDEX", "microsoft-docs-embeddings")
        
        # Azure OpenAI configuration for embeddings
        self.azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
        
        # Initialize clients
        self.search_client = None
        self.openai_client = None
        self._initialize_clients()
        
        # RAG configuration
        self.max_mcp_results = 5
        self.max_semantic_results = 10
        self.max_final_results = 8
        self.semantic_threshold = 0.75  # Minimum similarity score
        
    def _initialize_clients(self):
        """Initialize Azure AI Search and OpenAI clients"""
        try:
            if (AZURE_SEARCH_AVAILABLE and self.search_endpoint and self.search_key):
                self.search_client = SearchClient(
                    endpoint=self.search_endpoint,
                    index_name=self.search_index,
                    credential=AzureKeyCredential(self.search_key)
                )
                logger.info("✅ Azure AI Search client initialized")
            else:
                logger.warning("⚠️ Azure AI Search not available - using MCP only")
                
            if (AZURE_OPENAI_AVAILABLE and self.azure_openai_endpoint and self.azure_openai_key):
                self.openai_client = AsyncAzureOpenAI(
                    azure_endpoint=self.azure_openai_endpoint,
                    api_key=self.azure_openai_key,
                    api_version="2024-02-01"
                )
                logger.info("✅ Azure OpenAI client initialized")
            else:
                logger.warning("⚠️ Azure OpenAI not available - using MCP only")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize clients: {e}")
            self.search_client = None
            self.openai_client = None

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embeddings for text using Azure OpenAI"""
        if not self.openai_client:
            return None
            
        try:
            response = await self.openai_client.embeddings.create(
                input=text,
                model=self.embedding_model
            )
            embedding = response.data[0].embedding
            logger.debug(f"📊 Generated embedding with {len(embedding)} dimensions")
            return embedding
            
        except Exception as e:
            logger.error(f"❌ Failed to generate embedding: {e}")
            return None

    async def semantic_search(self, query: str, context: Dict) -> List[DocResult]:
        """Perform semantic search using Azure AI Search"""
        if not self.search_client or not self.openai_client:
            logger.debug("🔍 Semantic search unavailable - clients not initialized")
            return []
            
        try:
            # Generate query embedding
            query_embedding = await self.generate_embedding(query)
            if not query_embedding:
                return []
            
            # Enhance query with context
            enhanced_query = self._enhance_query(query, context)
            
            # Perform vector search
            vector_query = VectorizedQuery(
                vector=query_embedding,
                k_nearest_neighbors=self.max_semantic_results,
                fields="content_vector"
            )
            
            # Execute search with both vector and text
            results = self.search_client.search(
                search_text=enhanced_query,
                vector_queries=[vector_query],
                select=["title", "content", "url", "category", "architecture_types"],
                top=self.max_semantic_results
            )
            
            # Convert to DocResult objects
            doc_results = []
            for result in results:
                # Get search score (combination of vector similarity and text relevance)
                score = result.get('@search.score', 0.0)
                
                if score >= self.semantic_threshold:
                    doc_results.append(DocResult(
                        title=result.get('title', ''),
                        content=result.get('content', ''),
                        url=result.get('url', ''),
                        category=result.get('category', 'general'),
                        relevance_score=score,
                        source='semantic'
                    ))
            
            logger.info(f"🎯 Semantic search found {len(doc_results)} relevant docs")
            return doc_results
            
        except Exception as e:
            logger.error(f"❌ Semantic search failed: {e}")
            return []

    def _enhance_query(self, query: str, context: Dict) -> str:
        """Enhance search query with context information"""
        enhanced_parts = [query]
        
        # Add architecture type context
        if 'architecture_type' in context:
            enhanced_parts.append(f"architecture {context['architecture_type']}")
            
        # Add requirement context
        if 'requirements' in context:
            enhanced_parts.extend(context['requirements'])
            
        # Add Azure-specific terms
        enhanced_parts.extend(['Azure', 'Microsoft', 'cloud'])
        
        enhanced_query = ' '.join(enhanced_parts)
        logger.debug(f"🔍 Enhanced query: {enhanced_query}")
        return enhanced_query

    async def mcp_search(self, query: str) -> List[DocResult]:
        """Perform MCP search (existing functionality)"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.mcp_base_url}/mcp/call_tool",
                    json={
                        "tool": "microsoft_docs_search",
                        "arguments": {"query": query}
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, dict) and "content" in result:
                        docs = result["content"][:self.max_mcp_results]
                        
                        # Convert to DocResult objects
                        doc_results = []
                        for doc in docs:
                            if isinstance(doc, dict):
                                doc_results.append(DocResult(
                                    title=doc.get('title', ''),
                                    content=doc.get('content', ''),
                                    url=doc.get('contentUrl', ''),
                                    category='mcp',
                                    relevance_score=0.8,  # Default MCP score
                                    source='mcp'
                                ))
                        
                        logger.info(f"📡 MCP search found {len(doc_results)} docs")
                        return doc_results
                        
        except Exception as e:
            logger.warning(f"⚠️ MCP search failed: {e}")
            
        return []

    def _merge_and_rank(self, mcp_results: List[DocResult], semantic_results: List[DocResult]) -> List[DocResult]:
        """Merge and rank results from different sources"""
        
        # Combine results
        all_results = []
        seen_urls = set()
        
        # Add MCP results (prioritize live data)
        for result in mcp_results:
            if result.url not in seen_urls:
                result.relevance_score *= 1.2  # Boost MCP results (fresh data)
                all_results.append(result)
                seen_urls.add(result.url)
        
        # Add semantic results (deduplicate by URL)
        for result in semantic_results:
            if result.url not in seen_urls:
                all_results.append(result)
                seen_urls.add(result.url)
            else:
                # If same URL from different sources, boost the score
                for existing in all_results:
                    if existing.url == result.url:
                        existing.relevance_score = max(existing.relevance_score, result.relevance_score * 1.1)
                        existing.source = 'hybrid'
                        break
        
        # Sort by relevance score (highest first)
        ranked_results = sorted(all_results, key=lambda x: x.relevance_score, reverse=True)
        
        # Return top results
        final_results = ranked_results[:self.max_final_results]
        
        logger.info(f"🏆 Ranked results: {len(final_results)} final docs "
                   f"(MCP: {len(mcp_results)}, Semantic: {len(semantic_results)})")
        
        return final_results

    async def hybrid_search(self, query: str, context: Dict = None) -> List[Dict]:
        """Main hybrid search combining MCP and semantic search"""
        if context is None:
            context = {}
            
        logger.info(f"🔎 Starting hybrid search for: {query[:50]}...")
        
        # Execute both searches concurrently
        mcp_task = asyncio.create_task(self.mcp_search(query))
        semantic_task = asyncio.create_task(self.semantic_search(query, context))
        
        # Wait for both to complete
        mcp_results, semantic_results = await asyncio.gather(mcp_task, semantic_task, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(mcp_results, Exception):
            logger.error(f"❌ MCP search exception: {mcp_results}")
            mcp_results = []
        if isinstance(semantic_results, Exception):
            logger.error(f"❌ Semantic search exception: {semantic_results}")
            semantic_results = []
        
        # Merge and rank results
        final_results = self._merge_and_rank(mcp_results, semantic_results)
        
        # Convert back to original format for compatibility
        formatted_results = []
        for result in final_results:
            formatted_results.append({
                'title': result.title,
                'content': result.content,
                'contentUrl': result.url,
                'category': result.category,
                'relevance_score': result.relevance_score,
                'source': result.source
            })
        
        logger.info(f"✅ Hybrid search completed: {len(formatted_results)} results")
        return formatted_results

# Global enhanced service instance
enhanced_microsoft_docs_service = EnhancedMicrosoftDocsService()