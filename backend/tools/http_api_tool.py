"""
HTTP API Tool — Advanced HTTP client with retry, auth, and parsing.

Provides:
- REST API calls with various methods
- Authentication (Bearer, Basic, API Key)
- Retry logic with backoff
- Response parsing (JSON, XML, HTML)
- Rate limiting awareness
- Webhook verification
"""

import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass


@dataclass
class RateLimitInfo:
    remaining: int
    reset_at: Optional[float]
    limit: int


class HttpApiTool:
    """
    Advanced HTTP client for API interactions.
    """
    
    TOOL_NAME = "http_api"
    TOOL_DESCRIPTION = """
    Advanced HTTP client for API calls with built-in resilience.
    
    Features:
    - All HTTP methods (GET, POST, PUT, DELETE, PATCH)
    - Authentication: Bearer, Basic, API Key, Custom headers
    - Automatic retries with exponential backoff
    - Response parsing: JSON, XML, HTML, raw
    - Rate limit tracking
    - Timeout handling
    - Request/response logging
    
    Use for:
    - Calling external APIs
    - Webhook implementations
    - Data fetching from REST services
    - API testing and validation
    """
    
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx", "3xxxx"]
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limits: Dict[str, RateLimitInfo] = {}
        self._default_timeout = 30
        self._max_retries = 3
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict] = None,
        auth_type: Optional[str] = None,  # bearer, basic, api_key
        auth_value: Optional[str] = None,
        timeout: int = 30,
        retries: int = 3,
        parse_as: str = "json",  # json, xml, html, text, auto
        follow_redirects: bool = True,
        verify_ssl: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute HTTP request with resilience.
        """
        # Build headers
        request_headers = headers or {}
        
        # Add auth
        if auth_type == "bearer" and auth_value:
            request_headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "basic" and auth_value:
            import base64
            encoded = base64.b64encode(auth_value.encode()).decode()
            request_headers["Authorization"] = f"Basic {encoded}"
        elif auth_type == "api_key" and auth_value:
            request_headers["X-API-Key"] = auth_value
        
        # Check rate limits
        domain = self._extract_domain(url)
        if domain in self._rate_limits:
            rl = self._rate_limits[domain]
            if rl.remaining <= 0 and rl.reset_at and time.time() < rl.reset_at:
                wait_time = rl.reset_at - time.time()
                return {
                    "success": False,
                    "error": f"Rate limit exceeded. Reset in {wait_time:.0f}s",
                    "rate_limited": True
                }
        
        # Execute with retries
        last_error = None
        for attempt in range(retries):
            try:
                session = await self._get_session()
                
                start_time = time.time()
                
                async with session.request(
                    method=method.upper(),
                    url=url,
                    headers=request_headers,
                    params=params,
                    data=data,
                    json=json_data,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    ssl=verify_ssl,
                    allow_redirects=follow_redirects,
                ) as response:
                    
                    latency = time.time() - start_time
                    
                    # Update rate limits from headers
                    self._update_rate_limits(domain, response.headers)
                    
                    # Read response
                    body = await response.text()
                    
                    # Parse response
                    parsed_body = self._parse_response(body, parse_as, response.headers.get("content-type", ""))
                    
                    result = {
                        "success": 200 <= response.status < 300,
                        "status_code": response.status,
                        "url": str(response.url),
                        "method": method.upper(),
                        "latency_ms": round(latency * 1000, 2),
                        "headers": dict(response.headers),
                        "body": parsed_body if parsed_body else body[:10000],
                        "body_truncated": len(body) > 10000,
                        "size_bytes": len(body)
                    }
                    
                    # Handle non-2xx
                    if not result["success"]:
                        result["error"] = f"HTTP {response.status}: {response.reason}"
                    
                    return result
                    
            except asyncio.TimeoutError:
                last_error = f"Timeout after {timeout}s"
                if attempt < retries - 1:
                    wait = 2 ** attempt  # Exponential backoff
                    await asyncio.sleep(wait)
            except Exception as e:
                last_error = str(e)
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        # All retries failed
        return {
            "success": False,
            "error": f"Failed after {retries} attempts: {last_error}",
            "last_error": last_error
        }
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain for rate limit tracking."""
        from urllib.parse import urlparse
        return urlparse(url).netloc
    
    def _update_rate_limits(self, domain: str, headers: Dict[str, str]):
        """Update rate limit info from response headers."""
        remaining = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        limit = headers.get("X-RateLimit-Limit") or headers.get("x-ratelimit-limit")
        reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
        
        if remaining or limit:
            self._rate_limits[domain] = RateLimitInfo(
                remaining=int(remaining) if remaining else 999,
                reset_at=float(reset) if reset else None,
                limit=int(limit) if limit else 999
            )
    
    def _parse_response(self, body: str, parse_as: str, content_type: str) -> Any:
        """Parse response body."""
        if parse_as == "auto":
            if "json" in content_type:
                parse_as = "json"
            elif "xml" in content_type:
                parse_as = "xml"
            elif "html" in content_type:
                parse_as = "html"
            else:
                parse_as = "text"
        
        if parse_as == "json":
            try:
                import json
                return json.loads(body)
            except:
                return None
        elif parse_as == "xml":
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(body)
                return self._xml_to_dict(root)
            except:
                return None
        elif parse_as == "html":
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(body, 'html.parser')
                # Extract useful info
                return {
                    "title": soup.title.string if soup.title else None,
                    "text": soup.get_text(separator=' ', strip=True)[:5000],
                    "links": [a.get('href') for a in soup.find_all('a', href=True)][:50]
                }
            except:
                return None
        
        return None
    
    def _xml_to_dict(self, element) -> Any:
        """Simple XML to dict."""
        result = {}
        if element.attrib:
            result["@attributes"] = element.attrib
        for child in element:
            child_data = self._xml_to_dict(child)
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data
        text = element.text.strip() if element.text else ""
        if text:
            result["#text"] = text
        return result if result else text or None
    
    async def batch_request(
        self,
        requests: List[Dict[str, Any]],
        concurrency: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple requests with controlled concurrency.
        """
        semaphore = asyncio.Semaphore(concurrency)
        
        async def bounded_execute(req):
            async with semaphore:
                return await self.execute(**req)
        
        return await asyncio.gather(*[bounded_execute(r) for r in requests])
    
    async def close(self):
        """Close session."""
        if self._session and not self._session.closed:
            await self._session.close()


http_api_tool = HttpApiTool()