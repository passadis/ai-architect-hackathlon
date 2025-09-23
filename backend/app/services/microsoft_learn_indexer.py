#!/usr/bin/env python3
"""
Microsoft Learn Documentation Indexer for Azure AI Search

This service fetches Microsoft Learn content, generates embeddings,
and populates the Azure AI Search index for semantic search capabilities.
"""

import asyncio
import json
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import re
from urllib.parse import urlparse, urljoin

import httpx
from openai import AsyncAzureOpenAI
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType, VectorSearch,
    VectorSearchProfile, VectorSearchAlgorithmConfiguration,
    HnswAlgorithmConfiguration, VectorSearchAlgorithmKind
)
from azure.core.credentials import AzureKeyCredential

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MicrosoftLearnIndexer:
    """Service to index Microsoft Learn documentation with embeddings for semantic search"""
    
    def __init__(self):
        # Load configuration from environment
        self.azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("AZURE_OPENAI_KEY")
        self.embedding_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
        self.embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        
        # Azure AI Search configuration
        self.search_service_name = os.getenv("AZURE_SEARCH_SERVICE_NAME")
        self.search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.search_key = os.getenv("AZURE_SEARCH_API_KEY")
        self.search_index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "microsoft-docs")
        
        # MCP service configuration for document fetching
        self.mcp_base_url = os.getenv("MCP_HTTP_SERVICE_URL", "http://localhost:8001")
        
        # Initialize clients
        self._init_clients()
        
        # Document processing configuration
        self.chunk_size = 1000  # Characters per chunk
        self.chunk_overlap = 200  # Overlap between chunks
        self.max_docs_per_batch = 10  # Documents to process in parallel
        
    def _init_clients(self):
        """Initialize Azure OpenAI and Search clients"""
        try:
            # Initialize Azure OpenAI client for embeddings
            if self.azure_openai_endpoint and self.azure_openai_key:
                self.openai_client = AsyncAzureOpenAI(
                    api_key=self.azure_openai_key,
                    api_version="2024-12-01-preview",
                    azure_endpoint=self.azure_openai_endpoint
                )
                logger.info("✅ Azure OpenAI client initialized")
            else:
                raise ValueError("Azure OpenAI configuration missing")
            
            # Initialize Azure Search clients
            if self.search_endpoint and self.search_key:
                credential = AzureKeyCredential(self.search_key)
                self.search_index_client = SearchIndexClient(
                    endpoint=self.search_endpoint,
                    credential=credential
                )
                self.search_client = SearchClient(
                    endpoint=self.search_endpoint,
                    index_name=self.search_index_name,
                    credential=credential
                )
                logger.info("✅ Azure AI Search clients initialized")
            else:
                raise ValueError("Azure AI Search configuration missing")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize clients: {e}")
            raise
    
    async def create_search_index(self) -> bool:
        """Create the Azure AI Search index with vector fields"""
        try:
            logger.info(f"🔧 Creating search index: {self.search_index_name}")
            
            # Define the search index schema
            fields = [
                # Primary key
                SearchField(
                    name="id",
                    type=SearchFieldDataType.String,
                    key=True,
                    searchable=False,
                    filterable=True,
                    sortable=True
                ),
                
                # Document content and metadata
                SearchField(
                    name="title",
                    type=SearchFieldDataType.String,
                    searchable=True,
                    filterable=True,
                    sortable=True
                ),
                SearchField(
                    name="content",
                    type=SearchFieldDataType.String,
                    searchable=True,
                    analyzer_name="en.microsoft"
                ),
                SearchField(
                    name="url",
                    type=SearchFieldDataType.String,
                    searchable=False,
                    filterable=True
                ),
                SearchField(
                    name="source_type",
                    type=SearchFieldDataType.String,
                    searchable=False,
                    filterable=True
                ),
                SearchField(
                    name="category",
                    type=SearchFieldDataType.String,
                    searchable=True,
                    filterable=True,
                    facetable=True
                ),
                SearchField(
                    name="last_updated",
                    type=SearchFieldDataType.DateTimeOffset,
                    searchable=False,
                    filterable=True,
                    sortable=True
                ),
                SearchField(
                    name="chunk_index",
                    type=SearchFieldDataType.Int32,
                    searchable=False,
                    filterable=True,
                    sortable=True
                ),
                
                # Vector field for embeddings
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=1536,  # text-embedding-3-small dimensions
                    vector_search_profile_name="my-vector-config"
                )
            ]
            
            # Configure vector search
            vector_search = VectorSearch(
                profiles=[
                    VectorSearchProfile(
                        name="my-vector-config",
                        algorithm_configuration_name="my-hnsw"
                    )
                ],
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="my-hnsw",
                        kind=VectorSearchAlgorithmKind.HNSW,
                        parameters={
                            "m": 4,
                            "efConstruction": 400,
                            "efSearch": 500,
                            "metric": "cosine"
                        }
                    )
                ]
            )
            
            # Create the index
            index = SearchIndex(
                name=self.search_index_name,
                fields=fields,
                vector_search=vector_search
            )
            
            # Create or update the index
            result = self.search_index_client.create_or_update_index(index)
            logger.info(f"✅ Search index '{self.search_index_name}' created/updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create search index: {e}")
            return False
    
    async def fetch_microsoft_docs(self, queries: List[str], max_docs: int = 50) -> List[Dict[str, Any]]:
        """Fetch Microsoft Learn documentation using MCP tools"""
        documents = []
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                for query in queries:
                    logger.info(f"🔍 Fetching docs for query: '{query}'")
                    
                    # Use MCP microsoft_docs_search to find relevant documents
                    search_response = await client.post(
                        f"{self.mcp_base_url}/mcp/call_tool",
                        json={
                            "name": "microsoft_docs_search",
                            "arguments": {"query": query}
                        }
                    )
                    
                    if search_response.status_code == 200:
                        search_data = search_response.json()
                        
                        # Extract search results
                        if "result" in search_data and "content" in search_data["result"]:
                            content = search_data["result"]["content"]
                            if isinstance(content, list):
                                for item in content[:10]:  # Limit per query
                                    if isinstance(item, dict) and "text" in item:
                                        doc_text = item["text"]
                                        
                                        # Extract URL if available
                                        url_match = re.search(r'https?://[^\s]+', doc_text)
                                        doc_url = url_match.group(0) if url_match else None
                                        
                                        # Extract title (usually first line)
                                        lines = doc_text.strip().split('\n')
                                        title = lines[0][:100] if lines else f"Document for {query}"
                                        
                                        documents.append({
                                            "title": title.strip(),
                                            "content": doc_text,
                                            "url": doc_url,
                                            "source_query": query,
                                            "source_type": "microsoft_learn_search"
                                        })
                    
                    # If we have URLs, try to fetch full content
                    if len(documents) < max_docs:
                        # Extract unique URLs from the documents we found
                        unique_urls = set()
                        for doc in documents:
                            if doc.get("url"):
                                unique_urls.add(doc["url"])
                        
                        # Fetch full content for some URLs using microsoft_docs_fetch
                        for url in list(unique_urls)[:5]:  # Limit to 5 full fetches per query
                            if url and "microsoft.com" in url:
                                try:
                                    fetch_response = await client.post(
                                        f"{self.mcp_base_url}/mcp/call_tool",
                                        json={
                                            "name": "microsoft_docs_fetch",
                                            "arguments": {"url": url}
                                        }
                                    )
                                    
                                    if fetch_response.status_code == 200:
                                        fetch_data = fetch_response.json()
                                        if "result" in fetch_data and "content" in fetch_data["result"]:
                                            full_content = fetch_data["result"]["content"]
                                            if isinstance(full_content, list) and len(full_content) > 0:
                                                content_text = full_content[0].get("text", "")
                                                if len(content_text) > 500:  # Only if substantial content
                                                    documents.append({
                                                        "title": f"Full content: {url.split('/')[-1]}",
                                                        "content": content_text,
                                                        "url": url,
                                                        "source_query": query,
                                                        "source_type": "microsoft_learn_full"
                                                    })
                                except Exception as fetch_error:
                                    logger.warning(f"⚠️ Failed to fetch full content from {url}: {fetch_error}")
                    
                    if len(documents) >= max_docs:
                        break
        
        except Exception as e:
            logger.error(f"❌ Error fetching Microsoft docs: {e}")
        
        logger.info(f"📄 Fetched {len(documents)} documents")
        return documents[:max_docs]
    
    def chunk_document(self, content: str, title: str) -> List[str]:
        """Split document content into overlapping chunks for embedding"""
        if len(content) <= self.chunk_size:
            return [content]
        
        chunks = []
        start = 0
        
        while start < len(content):
            end = start + self.chunk_size
            
            # Try to break at a sentence or paragraph boundary
            if end < len(content):
                # Look for sentence endings
                for i in range(end, max(start + self.chunk_size // 2, end - 100), -1):
                    if content[i] in '.!?\n':
                        end = i + 1
                        break
            
            chunk = content[start:end].strip()
            if len(chunk) > 50:  # Only include substantial chunks
                chunks.append(chunk)
            
            start = end - self.chunk_overlap
            if start >= len(content):
                break
        
        return chunks
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts using Azure OpenAI"""
        try:
            logger.info(f"🧠 Generating embeddings for {len(texts)} texts")
            
            # Generate embeddings
            response = await self.openai_client.embeddings.create(
                input=texts,
                model=self.embedding_deployment
            )
            
            embeddings = [data.embedding for data in response.data]
            logger.info(f"✅ Generated {len(embeddings)} embeddings")
            return embeddings
            
        except Exception as e:
            logger.error(f"❌ Failed to generate embeddings: {e}")
            raise
    
    async def index_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """Index documents with embeddings into Azure AI Search"""
        try:
            logger.info(f"📝 Indexing {len(documents)} documents")
            
            search_documents = []
            texts_to_embed = []
            doc_metadata = []
            
            # Prepare documents and chunks for embedding
            for doc_idx, doc in enumerate(documents):
                content = doc.get("content", "")
                title = doc.get("title", f"Document {doc_idx}")
                
                # Create chunks
                chunks = self.chunk_document(content, title)
                
                for chunk_idx, chunk in enumerate(chunks):
                    # Create document ID
                    doc_id = hashlib.md5(f"{title}_{chunk_idx}_{chunk[:50]}".encode()).hexdigest()
                    
                    # Prepare for embedding
                    texts_to_embed.append(chunk)
                    doc_metadata.append({
                        "id": doc_id,
                        "title": title,
                        "content": chunk,
                        "url": doc.get("url", ""),
                        "source_type": doc.get("source_type", "microsoft_learn"),
                        "category": self._extract_category(doc.get("url", "")),
                        "last_updated": datetime.utcnow().isoformat() + "Z",
                        "chunk_index": chunk_idx
                    })
            
            # Generate embeddings in batches
            batch_size = 50  # Azure OpenAI embedding batch limit
            all_embeddings = []
            
            for i in range(0, len(texts_to_embed), batch_size):
                batch_texts = texts_to_embed[i:i + batch_size]
                batch_embeddings = await self.generate_embeddings(batch_texts)
                all_embeddings.extend(batch_embeddings)
            
            # Combine metadata with embeddings
            for metadata, embedding in zip(doc_metadata, all_embeddings):
                metadata["content_vector"] = embedding
                search_documents.append(metadata)
            
            # Upload to Azure AI Search in batches
            upload_batch_size = 100  # Search service batch limit
            total_uploaded = 0
            
            for i in range(0, len(search_documents), upload_batch_size):
                batch = search_documents[i:i + upload_batch_size]
                
                try:
                    result = self.search_client.upload_documents(documents=batch)
                    total_uploaded += len(batch)
                    logger.info(f"📤 Uploaded batch {i//upload_batch_size + 1}: {len(batch)} documents")
                except Exception as batch_error:
                    logger.error(f"❌ Failed to upload batch {i//upload_batch_size + 1}: {batch_error}")
                    continue
            
            logger.info(f"✅ Successfully indexed {total_uploaded} document chunks")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to index documents: {e}")
            return False
    
    def _extract_category(self, url: str) -> str:
        """Extract category from Microsoft Learn URL"""
        if not url:
            return "general"
        
        try:
            path = urlparse(url).path.lower()
            
            if "/azure/" in path:
                return "azure"
            elif "/dotnet/" in path:
                return "dotnet"
            elif "/microsoft-365/" in path:
                return "microsoft-365"
            elif "/power-platform/" in path:
                return "power-platform"
            elif "/windows/" in path:
                return "windows"
            else:
                return "general"
        except:
            return "general"
    
    async def run_full_indexing(self, custom_queries: Optional[List[str]] = None) -> bool:
        """Run the complete indexing pipeline"""
        try:
            logger.info("🚀 Starting Microsoft Learn indexing pipeline")
            
            # Step 1: Create search index
            if not await self.create_search_index():
                return False
            
            # Step 2: Define search queries for comprehensive coverage
            default_queries = [
                # Azure Core Services
                "Azure architecture best practices",
                "Azure Well-Architected Framework",
                "Azure compute services",
                "Azure storage solutions",
                "Azure networking fundamentals",
                "Azure security and identity",
                "Azure databases and data services",
                "Azure AI and machine learning",
                
                # Development and DevOps
                "Azure DevOps CI/CD pipelines",
                "Azure Container Apps deployment",
                "Azure Functions serverless",
                "Azure App Service web apps",
                "Infrastructure as Code Azure",
                "Azure Resource Manager templates",
                "Bicep template deployment",
                "Terraform Azure provider",
                
                # Monitoring and Management
                "Azure Monitor and logging",
                "Application Insights monitoring",
                "Azure cost optimization",
                "Azure governance and compliance",
                "Azure backup and disaster recovery",
                
                # Integration and APIs
                "Azure API Management",
                "Azure Service Bus messaging",
                "Azure Event Grid events",
                "Azure Logic Apps workflows",
                "Azure Integration Services"
            ]
            
            queries = custom_queries if custom_queries else default_queries
            
            # Step 3: Fetch documents
            documents = await self.fetch_microsoft_docs(queries, max_docs=200)
            
            if not documents:
                logger.warning("⚠️ No documents fetched for indexing")
                return False
            
            # Step 4: Index documents with embeddings
            success = await self.index_documents(documents)
            
            if success:
                logger.info("🎉 Microsoft Learn indexing completed successfully!")
                logger.info(f"📊 Total documents processed: {len(documents)}")
                return True
            else:
                logger.error("❌ Indexing failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Indexing pipeline failed: {e}")
            return False

async def main():
    """Main function to run the indexing process"""
    indexer = MicrosoftLearnIndexer()
    
    # Run the full indexing pipeline
    success = await indexer.run_full_indexing()
    
    if success:
        print("✅ Microsoft Learn indexing completed successfully!")
        print("🔍 Your enhanced RAG system is now ready for semantic search!")
    else:
        print("❌ Indexing failed. Check the logs for details.")

if __name__ == "__main__":
    asyncio.run(main())