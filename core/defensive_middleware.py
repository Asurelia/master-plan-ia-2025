"""
Defensive Middleware Stack
Implements security hardening based on 2025 best practices
"""

import asyncio
import json
import logging
import time
import traceback
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Any
import re

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.types import ASGIApp

from .secure_config import secure_config

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Security headers middleware with 2025 best practices"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.security_headers = {
            # HSTS - Force HTTPS for 1 year
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
            
            # Prevent MIME type sniffing
            "X-Content-Type-Options": "nosniff",
            
            # Prevent clickjacking
            "X-Frame-Options": "DENY",
            
            # XSS protection
            "X-XSS-Protection": "1; mode=block",
            
            # Referrer policy
            "Referrer-Policy": "strict-origin-when-cross-origin",
            
            # CSP - Strict content security policy
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            ),
            
            # Permissions policy
            "Permissions-Policy": (
                "camera=(), microphone=(), geolocation=(), "
                "payment=(), usb=(), magnetometer=(), gyroscope=()"
            ),
            
            # Cross-origin policies
            "Cross-Origin-Embedder-Policy": "require-corp",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-origin"
        }
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add security headers
        for header, value in self.security_headers.items():
            response.headers[header] = value
        
        # Add request ID for tracking
        request_id = str(uuid.uuid4())
        response.headers["X-Request-ID"] = request_id
        
        return response


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Advanced rate limiting with adaptive thresholds"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.requests = defaultdict(lambda: deque(maxlen=1000))
        self.blocked_ips = {}
        self.suspicious_ips = defaultdict(int)
        
        # Rate limits by endpoint type
        self.rate_limits = {
            "/auth/": {"requests": 5, "window": 300, "block_duration": 900},  # 5 per 5min
            "/voice/": {"requests": 20, "window": 60, "block_duration": 300},  # 20 per min
            "/api/": {"requests": 100, "window": 60, "block_duration": 60},    # 100 per min
            "default": {"requests": 60, "window": 60, "block_duration": 60}    # 60 per min
        }
    
    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        
        # Check if IP is blocked
        if await self._is_blocked(client_ip):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "message": "IP temporarily blocked due to rate limiting",
                    "retry_after": 300
                }
            )
        
        # Check rate limit
        if not await self._check_rate_limit(client_ip, request.url.path):
            await self._handle_rate_limit_violation(client_ip, request)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests from this IP",
                    "retry_after": 60
                }
            )
        
        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, handling proxies"""
        # Check for forwarded headers (from reverse proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host
    
    async def _check_rate_limit(self, ip: str, path: str) -> bool:
        """Check if request is within rate limits"""
        # Determine rate limit based on path
        limit_config = None
        for pattern, config in self.rate_limits.items():
            if pattern in path or pattern == "default":
                limit_config = config
                break
        
        if not limit_config:
            limit_config = self.rate_limits["default"]
        
        current_time = time.time()
        window_start = current_time - limit_config["window"]
        
        # Clean old requests
        ip_requests = self.requests[ip]
        while ip_requests and ip_requests[0] < window_start:
            ip_requests.popleft()
        
        # Check if limit exceeded
        if len(ip_requests) >= limit_config["requests"]:
            return False
        
        # Record this request
        ip_requests.append(current_time)
        return True
    
    async def _handle_rate_limit_violation(self, ip: str, request: Request):
        """Handle rate limit violation with escalation"""
        self.suspicious_ips[ip] += 1
        
        # Log suspicious activity
        logger.warning(
            f"Rate limit violation from {ip}",
            extra={
                "ip": ip,
                "path": request.url.path,
                "user_agent": request.headers.get("user-agent"),
                "violation_count": self.suspicious_ips[ip]
            }
        )
        
        # Escalate for repeated violations
        if self.suspicious_ips[ip] >= 5:
            await self._block_ip(ip, duration=1800)  # 30 minutes
            logger.error(f"IP {ip} blocked for repeated rate limit violations")
    
    async def _block_ip(self, ip: str, duration: int):
        """Block IP for specified duration"""
        self.blocked_ips[ip] = time.time() + duration
    
    async def _is_blocked(self, ip: str) -> bool:
        """Check if IP is currently blocked"""
        if ip not in self.blocked_ips:
            return False
        
        if time.time() > self.blocked_ips[ip]:
            del self.blocked_ips[ip]
            return False
        
        return True


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Defensive input validation middleware"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        
        # Dangerous patterns to detect
        self.dangerous_patterns = [
            # XSS patterns
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            
            # SQL injection patterns
            r'(union|select|insert|update|delete|drop|create|alter)\s+',
            r'(\-\-|\#|\/\*|\*\/)',
            r'(\bor\b|\band\b)\s+\d+\s*=\s*\d+',
            
            # Command injection patterns
            r'[;&|`$\(\){}[\]]',
            r'(exec|eval|system|shell_exec)',
            
            # Path traversal patterns
            r'(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)',
        ]
        
        # Compile patterns for performance
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.dangerous_patterns]
    
    async def dispatch(self, request: Request, call_next):
        # Skip validation for GET requests with no body
        if request.method == "GET":
            return await call_next(request)
        
        try:
            # Read and validate request body
            body = await request.body()
            if body:
                await self._validate_input(body, request)
        except ValueError as e:
            logger.warning(f"Input validation failed: {e}", extra={"ip": request.client.host})
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid input", "message": "Request contains potentially dangerous content"}
            )
        
        return await call_next(request)
    
    async def _validate_input(self, body: bytes, request: Request):
        """Validate request body for dangerous patterns"""
        try:
            # Decode body
            body_str = body.decode('utf-8')
            
            # Check for dangerous patterns
            for pattern in self.compiled_patterns:
                if pattern.search(body_str):
                    # Log security event
                    logger.error(
                        "Dangerous pattern detected in request",
                        extra={
                            "ip": request.client.host,
                            "path": request.url.path,
                            "pattern": pattern.pattern,
                            "user_agent": request.headers.get("user-agent")
                        }
                    )
                    raise ValueError(f"Dangerous pattern detected: {pattern.pattern}")
            
            # Additional JSON-specific validation
            if request.headers.get("content-type") == "application/json":
                try:
                    json_data = json.loads(body_str)
                    await self._validate_json_depth(json_data)
                    await self._validate_json_size(json_data)
                except json.JSONDecodeError:
                    raise ValueError("Invalid JSON format")
        
        except UnicodeDecodeError:
            raise ValueError("Invalid character encoding")
    
    async def _validate_json_depth(self, data: Any, depth: int = 0, max_depth: int = 10):
        """Prevent JSON bomb attacks with deep nesting"""
        if depth > max_depth:
            raise ValueError("JSON nesting too deep")
        
        if isinstance(data, dict):
            for value in data.values():
                await self._validate_json_depth(value, depth + 1, max_depth)
        elif isinstance(data, list):
            for item in data:
                await self._validate_json_depth(item, depth + 1, max_depth)
    
    async def _validate_json_size(self, data: Any, max_items: int = 1000):
        """Prevent JSON bomb attacks with large objects"""
        item_count = self._count_json_items(data)
        if item_count > max_items:
            raise ValueError("JSON object too large")
    
    def _count_json_items(self, data: Any) -> int:
        """Count total items in JSON object"""
        if isinstance(data, dict):
            return len(data) + sum(self._count_json_items(v) for v in data.values())
        elif isinstance(data, list):
            return len(data) + sum(self._count_json_items(item) for item in data)
        else:
            return 1


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Secure error handling middleware"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            return await self._handle_exception(request, exc)
    
    async def _handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        """Handle exceptions securely"""
        request_id = str(uuid.uuid4())
        
        # Log full error details securely
        logger.error(
            f"Unhandled exception: {type(exc).__name__}",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "ip": request.client.host,
                "user_agent": request.headers.get("user-agent"),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        
        # Determine response based on environment
        if secure_config.is_debug():
            # Development: include debug info
            content = {
                "error": "Internal server error",
                "request_id": request_id,
                "debug": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc().split('\n')
                }
            }
        else:
            # Production: minimal info
            content = {
                "error": "Internal server error",
                "request_id": request_id,
                "message": "An unexpected error occurred"
            }
        
        return JSONResponse(
            status_code=500,
            content=content
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Secure request logging middleware"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.sensitive_headers = {
            'authorization', 'cookie', 'x-api-key', 
            'x-auth-token', 'x-csrf-token'
        }
        self.sensitive_paths = {'/auth/', '/login', '/password'}
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # Log request (excluding sensitive data)
        await self._log_request(request, request_id)
        
        response = await call_next(request)
        
        # Log response
        duration = time.time() - start_time
        await self._log_response(request, response, request_id, duration)
        
        return response
    
    async def _log_request(self, request: Request, request_id: str):
        """Log request details securely"""
        # Filter sensitive headers
        safe_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in self.sensitive_headers
        }
        
        # Check if path is sensitive
        is_sensitive_path = any(path in str(request.url.path) for path in self.sensitive_paths)
        
        logger.info(
            "Request received",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query) if not is_sensitive_path else "[REDACTED]",
                "ip": request.client.host,
                "user_agent": request.headers.get("user-agent"),
                "headers": safe_headers,
                "sensitive_path": is_sensitive_path
            }
        )
    
    async def _log_response(self, request: Request, response: Response, request_id: str, duration: float):
        """Log response details securely"""
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "path": request.url.path,
                "method": request.method
            }
        )


def create_defensive_middleware_stack(app):
    """Create complete defensive middleware stack"""
    
    # HTTPS redirect in production
    if secure_config.is_production():
        app.add_middleware(HTTPSRedirectMiddleware)
    
    # Security headers (always enabled)
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Rate limiting
    app.add_middleware(RateLimitingMiddleware)
    
    # Input validation
    app.add_middleware(InputValidationMiddleware)
    
    # Error handling
    app.add_middleware(ErrorHandlingMiddleware)
    
    # Request logging
    app.add_middleware(RequestLoggingMiddleware)
    
    logger.info("Defensive middleware stack initialized")
    return app