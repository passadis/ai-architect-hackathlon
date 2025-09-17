#!/usr/bin/env python3
"""
Microsoft Learn Indexing Script

Run this script to populate the Azure AI Search index with Microsoft Learn documentation.
This enables semantic search capabilities in the enhanced RAG system.

Usage:
    python run_indexing.py

Environment Variables Required:
    - AZURE_OPENAI_ENDPOINT
    - AZURE_OPENAI_KEY (or use managed identity)
    - AZURE_OPENAI_EMBEDDING_DEPLOYMENT
    - AZURE_SEARCH_ENDPOINT
    - AZURE_SEARCH_API_KEY
    - AZURE_SEARCH_INDEX_NAME
    - MCP_HTTP_SERVICE_URL
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.append(str(backend_dir))

from app.services.microsoft_learn_indexer import MicrosoftLearnIndexer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main indexing function"""
    print("🚀 Microsoft Learn Documentation Indexer")
    print("=" * 50)
    
    # Check required environment variables
    required_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_SEARCH_ENDPOINT", 
        "AZURE_SEARCH_API_KEY"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n💡 Make sure to set these environment variables before running.")
        return False
    
    print("✅ Environment variables configured")
    print(f"🔗 Azure OpenAI Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
    print(f"🔍 Azure Search Endpoint: {os.getenv('AZURE_SEARCH_ENDPOINT')}")
    print(f"📦 Search Index Name: {os.getenv('AZURE_SEARCH_INDEX_NAME', 'microsoft-docs')}")
    print(f"🧠 Embedding Model: {os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', 'text-embedding-3-small')}")
    
    # Initialize indexer
    try:
        indexer = MicrosoftLearnIndexer()
        print("✅ Indexer initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize indexer: {e}")
        return False
    
    # Run indexing
    print("\n🔄 Starting indexing process...")
    print("   This may take several minutes depending on the number of documents")
    
    try:
        success = await indexer.run_full_indexing()
        
        if success:
            print("\n🎉 Indexing completed successfully!")
            print("📊 Your Azure AI Search index is now populated with Microsoft Learn content")
            print("🔍 Semantic search is now available in your RAG system!")
            print("\n💡 Next steps:")
            print("   1. Test hybrid search in your application")
            print("   2. Monitor search performance and relevance")
            print("   3. Consider running periodic updates to keep content fresh")
            return True
        else:
            print("\n❌ Indexing failed. Check the logs above for details.")
            return False
            
    except KeyboardInterrupt:
        print("\n⚠️ Indexing interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Indexing failed with error: {e}")
        return False

if __name__ == "__main__":
    # Change to the script directory
    os.chdir(Path(__file__).parent)
    
    # Run the indexing process
    success = asyncio.run(main())
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)