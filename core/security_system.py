"""
Advanced Security and Rate Limiting System
Préventive security measures against attacks and abuse
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any, Union
from ipaddress import ip_address, ip_network
import redis.asyncio as redis
import aiohttp
from dataclasses import asdict

from .observability_system import observability, AlertSeverity


class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventType(Enum):
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    MALICIOUS_PAYLOAD = "malicious_payload"
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    DDOS_ATTACK = "ddos_attack"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DATA_EXFILTRATION = "data_exfiltration"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"


@dataclass
class SecurityEvent:
    id: str
    event_type: SecurityEventType
    threat_level: ThreatLevel
    source_ip: str
    user_id: Optional[str]
    description: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    resolved: bool = False


@dataclass
class RateLimitRule:
    name: str
    max_requests: int
    window_seconds: int
    key_pattern: str  # e.g., "ip:{ip}" or "user:{user_id}"
    burst_multiplier: float = 1.5
    block_duration: int = 300  # 5 minutes


@dataclass
class SecurityRule:
    name: str
    pattern: str
    rule_type: str  # "regex", "ip_range", "user_agent", etc.
    action: str     # "block", "monitor", "alert"
    threat_level: ThreatLevel
    description: str
    enabled: bool = True


class SecuritySystem:
    """
    Advanced security system with rate limiting, threat detection, and prevention
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        
        # Rate limiting
        self.rate_limits: Dict[str, RateLimitRule] = {}
        self.request_counts: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.blocked_ips: Dict[str, datetime] = {}
        self.blocked_users: Dict[str, datetime] = {}
        
        # Security rules
        self.security_rules: Dict[str, SecurityRule] = {}
        self.security_events: List[SecurityEvent] = []
        
        # Threat intelligence
        self.known_malicious_ips: Set[str] = set()
        self.suspicious_patterns: Dict[str, int] = defaultdict(int)
        self.user_behavior_baselines: Dict[str, Dict[str, Any]] = {}
        
        # IP reputation and geolocation
        self.ip_reputation_cache: Dict[str, Dict[str, Any]] = {}
        self.geo_cache: Dict[str, Dict[str, Any]] = {}
        
        # Monitoring
        self.security_metrics = {
            "blocked_requests": 0,
            "security_events": 0,
            "rate_limit_violations": 0,
            "threats_detected": 0
        }
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the security system"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            self.logger.info("✅ Security system initialized with Redis")
        except Exception as e:
            self.logger.warning(f"⚠️ Redis unavailable for security system: {e}")
            self.redis_client = None
        
        # Load default security rules
        await self._load_default_rules()
        
        # Start background tasks
        asyncio.create_task(self._cleanup_expired_blocks())
        asyncio.create_task(self._update_threat_intelligence())
        asyncio.create_task(self._analyze_security_events())
    
    async def _load_default_rules(self):
        """Load default security rules"""
        
        # Rate limiting rules
        self.rate_limits.update({
            "api_general": RateLimitRule(
                name="api_general",
                max_requests=100,
                window_seconds=60,
                key_pattern="ip:{ip}",
                burst_multiplier=1.2
            ),
            "api_auth": RateLimitRule(
                name="api_auth",
                max_requests=5,
                window_seconds=60,
                key_pattern="ip:{ip}",
                burst_multiplier=1.0,
                block_duration=900  # 15 minutes
            ),
            "api_voice": RateLimitRule(
                name="api_voice",
                max_requests=10,
                window_seconds=60,
                key_pattern="user:{user_id}",
                burst_multiplier=1.5
            ),
            "api_user": RateLimitRule(
                name="api_user",
                max_requests=1000,
                window_seconds=3600,
                key_pattern="user:{user_id}",
                burst_multiplier=1.3
            )
        })
        
        # Security rules
        self.security_rules.update({
            "sql_injection": SecurityRule(
                name="sql_injection",
                pattern=r"(union|select|insert|update|delete|drop|create|alter|exec|execute)\s+.*(\-\-|\/\*|\*\/)",
                rule_type="regex",
                action="block",
                threat_level=ThreatLevel.HIGH,
                description="Potential SQL injection attack"
            ),
            "xss_attack": SecurityRule(
                name="xss_attack",
                pattern=r"<script[^>]*>.*?</script>|javascript:|on\w+\s*=",
                rule_type="regex",
                action="block",
                threat_level=ThreatLevel.HIGH,
                description="Potential XSS attack"
            ),
            "path_traversal": SecurityRule(
                name="path_traversal",
                pattern=r"(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)",
                rule_type="regex",
                action="block",
                threat_level=ThreatLevel.MEDIUM,
                description="Path traversal attempt"
            ),
            "command_injection": SecurityRule(
                name="command_injection",
                pattern=r"[;&|`$\(\){}[\]]",
                rule_type="regex",
                action="monitor",
                threat_level=ThreatLevel.MEDIUM,
                description="Potential command injection"
            ),
            "suspicious_user_agent": SecurityRule(
                name="suspicious_user_agent",
                pattern=r"(bot|crawler|spider|scraper|hack|attack|scan|test|curl|wget|python|java|go-http)",
                rule_type="regex",
                action="monitor",
                threat_level=ThreatLevel.LOW,
                description="Suspicious User-Agent"
            )
        })
    
    # Rate Limiting
    
    async def check_rate_limit(self, key: str, rule_name: str, 
                              ip: str = None, user_id: str = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is within rate limits
        Returns (allowed, info)
        """
        if rule_name not in self.rate_limits:
            return True, {"error": "Rate limit rule not found"}
        
        rule = self.rate_limits[rule_name]
        
        # Format key with actual values
        if ip:
            key = key.format(ip=ip)
        if user_id:
            key = key.format(user_id=user_id)
        
        current_time = time.time()
        window_start = current_time - rule.window_seconds
        
        # Get request history
        if self.redis_client:
            requests = await self._get_redis_rate_limit_data(key, window_start)
        else:
            requests = [t for t in self.request_counts[key] if t > window_start]
        
        # Count requests in window
        request_count = len(requests)
        
        # Check if limit exceeded
        max_allowed = int(rule.max_requests * rule.burst_multiplier)
        if request_count >= max_allowed:
            # Rate limit exceeded
            await self._handle_rate_limit_violation(key, rule, ip, user_id)
            return False, {
                "rate_limited": True,
                "requests_made": request_count,
                "max_requests": rule.max_requests,
                "window_seconds": rule.window_seconds,
                "retry_after": rule.block_duration
            }
        
        # Record this request
        await self._record_request(key, current_time)
        
        return True, {
            "rate_limited": False,
            "requests_made": request_count,
            "max_requests": rule.max_requests,
            "window_seconds": rule.window_seconds,
            "remaining": max_allowed - request_count - 1
        }
    
    async def _get_redis_rate_limit_data(self, key: str, window_start: float) -> List[float]:
        """Get rate limit data from Redis"""
        try:
            data = await self.redis_client.zrangebyscore(f"rate_limit:{key}", window_start, "+inf")
            return [float(d) for d in data]
        except Exception as e:
            self.logger.error(f"Redis rate limit data error: {e}")
            return []
    
    async def _record_request(self, key: str, timestamp: float):
        """Record a request for rate limiting"""
        if self.redis_client:
            try:
                await self.redis_client.zadd(f"rate_limit:{key}", {str(timestamp): timestamp})
                await self.redis_client.expire(f"rate_limit:{key}", 3600)  # 1 hour TTL
            except Exception as e:
                self.logger.error(f"Redis record request error: {e}")
        else:
            self.request_counts[key].append(timestamp)
    
    async def _handle_rate_limit_violation(self, key: str, rule: RateLimitRule, 
                                         ip: str = None, user_id: str = None):
        """Handle rate limit violation"""
        self.security_metrics["rate_limit_violations"] += 1
        
        # Create security event
        await self._create_security_event(
            SecurityEventType.RATE_LIMIT_EXCEEDED,
            ThreatLevel.MEDIUM,
            ip or "unknown",
            user_id,
            f"Rate limit exceeded for rule {rule.name}",
            {"rule": rule.name, "key": key}
        )
        
        # Block IP/user if configured
        if rule.block_duration > 0:
            if ip:
                self.blocked_ips[ip] = datetime.now() + timedelta(seconds=rule.block_duration)
            if user_id:
                self.blocked_users[user_id] = datetime.now() + timedelta(seconds=rule.block_duration)
        
        # Record metric
        observability.increment_counter(
            "security_rate_limit_violations_total",
            labels={"rule": rule.name, "key_type": "ip" if ip else "user"}
        )
    
    # Security Rules and Threat Detection
    
    async def analyze_request(self, request_data: Dict[str, Any]) -> Tuple[bool, List[SecurityEvent]]:
        """
        Analyze a request for security threats
        Returns (allowed, security_events)
        """
        events = []
        allowed = True
        
        ip = request_data.get("ip", "unknown")
        user_id = request_data.get("user_id")
        user_agent = request_data.get("user_agent", "")
        path = request_data.get("path", "")
        method = request_data.get("method", "")
        payload = request_data.get("payload", "")
        
        # Check if IP/user is blocked
        if await self._is_blocked(ip, user_id):
            return False, events
        
        # Check against security rules
        for rule_name, rule in self.security_rules.items():
            if not rule.enabled:
                continue
            
            threat_detected = False
            
            if rule.rule_type == "regex":
                # Check all request data against regex
                combined_data = f"{path} {payload} {user_agent}"
                if re.search(rule.pattern, combined_data, re.IGNORECASE):
                    threat_detected = True
            
            elif rule.rule_type == "ip_range":
                try:
                    if ip_address(ip) in ip_network(rule.pattern):
                        threat_detected = True
                except:
                    pass
            
            elif rule.rule_type == "user_agent":
                if re.search(rule.pattern, user_agent, re.IGNORECASE):
                    threat_detected = True
            
            if threat_detected:
                event = await self._create_security_event(
                    SecurityEventType.SUSPICIOUS_ACTIVITY,
                    rule.threat_level,
                    ip,
                    user_id,
                    f"Security rule triggered: {rule.description}",
                    {"rule": rule_name, "pattern": rule.pattern}
                )
                events.append(event)
                
                if rule.action == "block":
                    allowed = False
                    event.blocked = True
                
                # Record pattern for learning
                self.suspicious_patterns[rule_name] += 1
        
        # Advanced threat detection
        await self._check_behavioral_anomalies(ip, user_id, request_data, events)
        await self._check_ip_reputation(ip, events)
        
        return allowed, events
    
    async def _is_blocked(self, ip: str, user_id: str = None) -> bool:
        """Check if IP or user is blocked"""
        current_time = datetime.now()
        
        # Check IP block
        if ip in self.blocked_ips:
            if current_time < self.blocked_ips[ip]:
                return True
            else:
                del self.blocked_ips[ip]
        
        # Check user block
        if user_id and user_id in self.blocked_users:
            if current_time < self.blocked_users[user_id]:
                return True
            else:
                del self.blocked_users[user_id]
        
        return False
    
    async def _check_behavioral_anomalies(self, ip: str, user_id: str, 
                                        request_data: Dict[str, Any], 
                                        events: List[SecurityEvent]):
        """Check for behavioral anomalies"""
        
        # Check for rapid sequential requests (potential bot)
        if user_id:
            user_key = f"behavior:{user_id}"
            recent_requests = self.request_counts[user_key]
            
            if len(recent_requests) > 10:
                # Check if all requests are within 1 second (bot-like behavior)
                recent_times = list(recent_requests)[-10:]
                if max(recent_times) - min(recent_times) < 1:
                    event = await self._create_security_event(
                        SecurityEventType.ANOMALOUS_BEHAVIOR,
                        ThreatLevel.MEDIUM,
                        ip,
                        user_id,
                        "Rapid sequential requests detected (bot-like behavior)",
                        {"request_pattern": "rapid_sequential"}
                    )
                    events.append(event)
        
        # Check for unusual request patterns
        path = request_data.get("path", "")
        method = request_data.get("method", "")
        
        # Detect path scanning
        if any(pattern in path.lower() for pattern in ["admin", "config", "backup", "test", "dev"]):
            event = await self._create_security_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                ThreatLevel.LOW,
                ip,
                user_id,
                f"Suspicious path access: {path}",
                {"suspicious_path": path}
            )
            events.append(event)
    
    async def _check_ip_reputation(self, ip: str, events: List[SecurityEvent]):
        """Check IP reputation against threat intelligence"""
        if ip in self.known_malicious_ips:
            event = await self._create_security_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                ThreatLevel.HIGH,
                ip,
                None,
                "Request from known malicious IP",
                {"ip_reputation": "malicious"}
            )
            events.append(event)
        
        # Check if IP is from suspicious geolocation
        geo_info = await self._get_ip_geolocation(ip)
        if geo_info and geo_info.get("country") in ["XX", "ZZ"]:  # Suspicious countries
            event = await self._create_security_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                ThreatLevel.LOW,
                ip,
                None,
                f"Request from suspicious geolocation: {geo_info.get('country')}",
                {"geolocation": geo_info}
            )
            events.append(event)
    
    async def _get_ip_geolocation(self, ip: str) -> Optional[Dict[str, Any]]:
        """Get IP geolocation (cached)"""
        if ip in self.geo_cache:
            return self.geo_cache[ip]
        
        try:
            # Use a free geolocation service (replace with your preferred provider)
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://ip-api.com/json/{ip}") as response:
                    if response.status == 200:
                        data = await response.json()
                        self.geo_cache[ip] = data
                        return data
        except Exception as e:
            self.logger.error(f"Geolocation lookup error: {e}")
        
        return None
    
    async def _create_security_event(self, event_type: SecurityEventType, 
                                   threat_level: ThreatLevel, ip: str, 
                                   user_id: Optional[str], description: str,
                                   metadata: Dict[str, Any] = None) -> SecurityEvent:
        """Create a security event"""
        event = SecurityEvent(
            id=f"sec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.security_events)}",
            event_type=event_type,
            threat_level=threat_level,
            source_ip=ip,
            user_id=user_id,
            description=description,
            metadata=metadata or {}
        )
        
        self.security_events.append(event)
        self.security_metrics["security_events"] += 1
        
        # Create alert for high/critical threats
        if threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            await observability.create_alert(
                AlertSeverity.HIGH if threat_level == ThreatLevel.HIGH else AlertSeverity.CRITICAL,
                f"Security threat detected: {description}",
                "security",
                "threat_detection",
                1,
                0,
                {"event_id": event.id, "threat_level": threat_level.value}
            )
        
        # Record security metrics
        observability.increment_counter(
            "security_events_total",
            labels={
                "event_type": event_type.value,
                "threat_level": threat_level.value,
                "source_ip": ip[:8] + "..." if len(ip) > 8 else ip  # Truncate for privacy
            }
        )
        
        return event
    
    # Background Tasks
    
    async def _cleanup_expired_blocks(self):
        """Clean up expired IP and user blocks"""
        while True:
            try:
                current_time = datetime.now()
                
                # Clean expired IP blocks
                expired_ips = [ip for ip, expires in self.blocked_ips.items() if current_time >= expires]
                for ip in expired_ips:
                    del self.blocked_ips[ip]
                
                # Clean expired user blocks
                expired_users = [user for user, expires in self.blocked_users.items() if current_time >= expires]
                for user in expired_users:
                    del self.blocked_users[user]
                
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                self.logger.error(f"Block cleanup error: {e}")
                await asyncio.sleep(60)
    
    async def _update_threat_intelligence(self):
        """Update threat intelligence data"""
        while True:
            try:
                # Update known malicious IPs from threat feeds
                # This is a placeholder - integrate with real threat intelligence feeds
                await self._fetch_threat_intelligence()
                await asyncio.sleep(3600)  # Update every hour
            except Exception as e:
                self.logger.error(f"Threat intelligence update error: {e}")
                await asyncio.sleep(3600)
    
    async def _fetch_threat_intelligence(self):
        """Fetch threat intelligence from external sources"""
        # Placeholder for threat intelligence integration
        # In production, integrate with services like:
        # - VirusTotal
        # - AbuseIPDB
        # - OpenThreatExchange
        # - Custom threat feeds
        pass
    
    async def _analyze_security_events(self):
        """Analyze security events for patterns and automated responses"""
        while True:
            try:
                # Analyze recent events for patterns
                recent_events = [e for e in self.security_events if 
                               datetime.now() - e.timestamp < timedelta(minutes=15)]
                
                # Detect DDoS attacks
                if len(recent_events) > 100:
                    # Potential DDoS - check if events are from multiple IPs
                    unique_ips = set(e.source_ip for e in recent_events)
                    if len(unique_ips) > 10:
                        await self._handle_ddos_attack(recent_events)
                
                # Detect brute force attacks
                auth_events = [e for e in recent_events if "auth" in e.description.lower()]
                if len(auth_events) > 10:
                    await self._handle_brute_force_attack(auth_events)
                
                await asyncio.sleep(300)  # Analyze every 5 minutes
            except Exception as e:
                self.logger.error(f"Security analysis error: {e}")
                await asyncio.sleep(300)
    
    async def _handle_ddos_attack(self, events: List[SecurityEvent]):
        """Handle potential DDoS attack"""
        source_ips = [e.source_ip for e in events]
        
        # Block top attacking IPs
        ip_counts = defaultdict(int)
        for ip in source_ips:
            ip_counts[ip] += 1
        
        for ip, count in ip_counts.items():
            if count > 5:  # Threshold for DDoS participation
                self.blocked_ips[ip] = datetime.now() + timedelta(hours=1)
        
        # Create critical alert
        await observability.create_alert(
            AlertSeverity.CRITICAL,
            f"DDoS attack detected: {len(events)} events from {len(set(source_ips))} IPs",
            "security",
            "ddos_detection",
            len(events),
            100,
            {"unique_ips": len(set(source_ips)), "blocked_ips": len(ip_counts)}
        )
    
    async def _handle_brute_force_attack(self, events: List[SecurityEvent]):
        """Handle brute force attack"""
        # Block IPs with multiple auth failures
        ip_failures = defaultdict(int)
        for event in events:
            ip_failures[event.source_ip] += 1
        
        for ip, failures in ip_failures.items():
            if failures >= 5:
                self.blocked_ips[ip] = datetime.now() + timedelta(hours=2)
        
        # Create alert
        await observability.create_alert(
            AlertSeverity.HIGH,
            f"Brute force attack detected: {len(events)} auth attempts",
            "security",
            "brute_force_detection",
            len(events),
            10,
            {"blocked_ips": len([ip for ip, failures in ip_failures.items() if failures >= 5])}
        )
    
    # API Methods
    
    def get_security_metrics(self) -> Dict[str, Any]:
        """Get security metrics"""
        return {
            **self.security_metrics,
            "blocked_ips": len(self.blocked_ips),
            "blocked_users": len(self.blocked_users),
            "security_rules": len(self.security_rules),
            "recent_events": len([e for e in self.security_events if 
                                datetime.now() - e.timestamp < timedelta(hours=1)])
        }
    
    def get_security_events(self, limit: int = 100) -> List[SecurityEvent]:
        """Get recent security events"""
        return sorted(self.security_events, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def get_blocked_entities(self) -> Dict[str, Any]:
        """Get blocked IPs and users"""
        return {
            "blocked_ips": {ip: expires.isoformat() for ip, expires in self.blocked_ips.items()},
            "blocked_users": {user: expires.isoformat() for user, expires in self.blocked_users.items()}
        }
    
    async def unblock_ip(self, ip: str) -> bool:
        """Manually unblock an IP"""
        if ip in self.blocked_ips:
            del self.blocked_ips[ip]
            return True
        return False
    
    async def unblock_user(self, user_id: str) -> bool:
        """Manually unblock a user"""
        if user_id in self.blocked_users:
            del self.blocked_users[user_id]
            return True
        return False


# Global instance
security_system = SecuritySystem()


# Decorators for FastAPI integration

def security_check(rule_name: str = "api_general"):
    """Decorator for FastAPI endpoints to check security"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract request info from FastAPI request
            request = kwargs.get('request')
            if not request:
                return await func(*args, **kwargs)
            
            # Get client info
            client_ip = request.client.host
            user_id = getattr(request.state, 'user_id', None)
            
            # Check rate limit
            allowed, rate_info = await security_system.check_rate_limit(
                f"ip:{client_ip}",
                rule_name,
                ip=client_ip,
                user_id=user_id
            )
            
            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(rate_info.get("retry_after", 60))}
                )
            
            # Analyze request for threats
            request_data = {
                "ip": client_ip,
                "user_id": user_id,
                "path": str(request.url.path),
                "method": request.method,
                "user_agent": request.headers.get("user-agent", ""),
                "payload": str(request.url.query)
            }
            
            allowed, security_events = await security_system.analyze_request(request_data)
            
            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=403,
                    detail="Request blocked by security system"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# Usage example
if __name__ == "__main__":
    async def example_usage():
        await security_system.initialize()
        
        # Simulate request analysis
        request_data = {
            "ip": "192.168.1.100",
            "user_id": "user123",
            "path": "/api/users",
            "method": "GET",
            "user_agent": "Mozilla/5.0",
            "payload": "id=1"
        }
        
        allowed, events = await security_system.analyze_request(request_data)
        print(f"Request allowed: {allowed}")
        print(f"Security events: {len(events)}")
        
        # Check rate limit
        allowed, info = await security_system.check_rate_limit(
            "ip:192.168.1.100",
            "api_general",
            ip="192.168.1.100"
        )
        print(f"Rate limit: {allowed}, info: {info}")
    
    asyncio.run(example_usage())