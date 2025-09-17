// Test script to verify diagram URL construction
const API_BASE_URL = 'https://backend.wonderfultree-bbb5e3f6.eastus2.azurecontainerapps.io';

const API_ENDPOINTS = {
  GENERATE_ARCHITECTURE: `${API_BASE_URL}/api/generate-architecture`,
};

// Test diagram URL from recent generation
const diagramUrl = "https://staiarchitectweb.blob.core.windows.net/diagrams/e2244011-0da5-4af2-b75a-5c08426b8c9e.png";

console.log("Original diagram URL:", diagramUrl);

// Simulate frontend logic
if (diagramUrl.startsWith('https://') && diagramUrl.includes('.blob.core.windows.net')) {
  const backendUrl = API_ENDPOINTS.GENERATE_ARCHITECTURE.replace(/\/api\/generate-architecture$/, '');
  const encoded = encodeURIComponent(diagramUrl);
  const proxyUrl = `${backendUrl}/api/proxy/diagram?url=${encoded}`;
  
  console.log("Backend URL:", backendUrl);
  console.log("Encoded URL:", encoded);
  console.log("Final proxy URL:", proxyUrl);
}