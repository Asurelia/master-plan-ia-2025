"""
Advanced Observability System for Master Plan IA
Préventive monitoring, alerting, and observability to anticipate ecosystem problems
"""

import asyncio
import json
import logging
import psutil
import time
import threading
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Union
from pathlib import Path
import aiohttp
import redis.asyncio as redis
import numpy as np
from dataclasses import asdict


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Metric:
    name: str
    value: Union[int, float]
    metric_type: MetricType
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""


@dataclass
class Alert:
    id: str
    severity: AlertSeverity
    message: str
    component: str
    metric_name: str
    current_value: Union[int, float]
    threshold: Union[int, float]
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheck:
    name: str
    status: str
    latency_ms: float
    last_check: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    name: str
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    failure_threshold: int = 5
    timeout: int = 60  # seconds
    last_failure: Optional[datetime] = None
    success_count: int = 0
    half_open_max_calls: int = 3


class ObservabilitySystem:
    """
    Advanced observability system with predictive capabilities
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.alerts: List[Alert] = []
        self.health_checks: Dict[str, HealthCheck] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.alert_handlers: List[Callable] = []
        self.is_running = False
        self.background_tasks = set()
        
        # Performance tracking
        self.request_metrics = defaultdict(lambda: deque(maxlen=100))
        self.error_patterns = defaultdict(int)
        self.anomaly_detection = AnomalyDetector()
        
        # System metrics
        self.system_metrics_interval = 5  # seconds
        self.health_check_interval = 30   # seconds
        self.alert_check_interval = 10    # seconds
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the observability system"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            self.logger.info("✅ Observability system initialized with Redis")
        except Exception as e:
            self.logger.warning(f"⚠️ Redis unavailable, using in-memory storage: {e}")
            self.redis_client = None
        
        # Start background tasks
        self.is_running = True
        self.background_tasks.add(asyncio.create_task(self._system_metrics_loop()))
        self.background_tasks.add(asyncio.create_task(self._health_check_loop()))
        self.background_tasks.add(asyncio.create_task(self._alert_check_loop()))
        self.background_tasks.add(asyncio.create_task(self._anomaly_detection_loop()))
    
    async def shutdown(self):
        """Shutdown the observability system"""
        self.is_running = False
        
        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        if self.redis_client:
            await self.redis_client.close()
    
    # Metrics Collection
    
    def record_metric(self, name: str, value: Union[int, float], 
                     metric_type: MetricType = MetricType.GAUGE,
                     labels: Dict[str, str] = None, unit: str = ""):
        """Record a metric with timestamp"""
        metric = Metric(
            name=name,
            value=value,
            metric_type=metric_type,
            labels=labels or {},
            unit=unit
        )
        
        self.metrics[name].append(metric)
        
        # Store in Redis for persistence
        if self.redis_client:
            asyncio.create_task(self._store_metric_redis(metric))
    
    async def _store_metric_redis(self, metric: Metric):
        """Store metric in Redis"""
        try:
            key = f"metric:{metric.name}:{metric.timestamp.isoformat()}"
            await self.redis_client.setex(key, 3600, json.dumps(asdict(metric), default=str))
        except Exception as e:
            self.logger.error(f"Failed to store metric in Redis: {e}")
    
    def increment_counter(self, name: str, value: int = 1, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        self.record_metric(name, value, MetricType.COUNTER, labels)
    
    def set_gauge(self, name: str, value: Union[int, float], labels: Dict[str, str] = None):
        """Set a gauge metric"""
        self.record_metric(name, value, MetricType.GAUGE, labels)
    
    def record_histogram(self, name: str, value: Union[int, float], labels: Dict[str, str] = None):
        """Record a histogram metric"""
        self.record_metric(name, value, MetricType.HISTOGRAM, labels)
    
    @asynccontextmanager
    async def time_operation(self, operation_name: str, labels: Dict[str, str] = None):
        """Context manager to time operations"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.record_metric(
                f"{operation_name}_duration_seconds",
                duration,
                MetricType.TIMER,
                labels,
                "seconds"
            )
    
    # Health Checks
    
    def register_health_check(self, name: str, check_func: Callable):
        """Register a health check function"""
        self.health_checks[name] = HealthCheck(
            name=name,
            status="unknown",
            latency_ms=0,
            last_check=datetime.now(),
            metadata={"check_func": check_func}
        )
    
    async def run_health_check(self, name: str) -> HealthCheck:
        """Run a specific health check"""
        if name not in self.health_checks:
            raise ValueError(f"Health check {name} not registered")
        
        check = self.health_checks[name]
        check_func = check.metadata["check_func"]
        
        start_time = time.time()
        try:
            result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
            check.status = "healthy" if result else "unhealthy"
            check.latency_ms = (time.time() - start_time) * 1000
            check.last_check = datetime.now()
        except Exception as e:
            check.status = "error"
            check.latency_ms = (time.time() - start_time) * 1000
            check.last_check = datetime.now()
            check.metadata["error"] = str(e)
        
        return check
    
    async def run_all_health_checks(self) -> Dict[str, HealthCheck]:
        """Run all registered health checks"""
        results = {}
        for name in self.health_checks:
            results[name] = await self.run_health_check(name)
        return results
    
    # Circuit Breaker
    
    def register_circuit_breaker(self, name: str, failure_threshold: int = 5, 
                                timeout: int = 60, half_open_max_calls: int = 3):
        """Register a circuit breaker"""
        self.circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            timeout=timeout,
            half_open_max_calls=half_open_max_calls
        )
    
    async def call_with_circuit_breaker(self, name: str, func: Callable, *args, **kwargs):
        """Call a function with circuit breaker protection"""
        if name not in self.circuit_breakers:
            self.register_circuit_breaker(name)
        
        breaker = self.circuit_breakers[name]
        
        # Check circuit breaker state
        if breaker.state == CircuitBreakerState.OPEN:
            if datetime.now() - breaker.last_failure > timedelta(seconds=breaker.timeout):
                breaker.state = CircuitBreakerState.HALF_OPEN
                breaker.success_count = 0
            else:
                raise Exception(f"Circuit breaker {name} is OPEN")
        
        if breaker.state == CircuitBreakerState.HALF_OPEN:
            if breaker.success_count >= breaker.half_open_max_calls:
                raise Exception(f"Circuit breaker {name} is HALF_OPEN, max calls reached")
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Success
            if breaker.state == CircuitBreakerState.HALF_OPEN:
                breaker.success_count += 1
                if breaker.success_count >= breaker.half_open_max_calls:
                    breaker.state = CircuitBreakerState.CLOSED
                    breaker.failure_count = 0
            else:
                breaker.failure_count = 0
            
            return result
            
        except Exception as e:
            # Failure
            breaker.failure_count += 1
            breaker.last_failure = datetime.now()
            
            if breaker.failure_count >= breaker.failure_threshold:
                breaker.state = CircuitBreakerState.OPEN
            
            raise e
    
    # Alerting
    
    def add_alert_handler(self, handler: Callable):
        """Add an alert handler function"""
        self.alert_handlers.append(handler)
    
    async def create_alert(self, severity: AlertSeverity, message: str, 
                          component: str, metric_name: str, 
                          current_value: Union[int, float], threshold: Union[int, float],
                          metadata: Dict[str, Any] = None):
        """Create and process an alert"""
        alert = Alert(
            id=f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.alerts)}",
            severity=severity,
            message=message,
            component=component,
            metric_name=metric_name,
            current_value=current_value,
            threshold=threshold,
            metadata=metadata or {}
        )
        
        self.alerts.append(alert)
        
        # Process alert handlers
        for handler in self.alert_handlers:
            try:
                await handler(alert) if asyncio.iscoroutinefunction(handler) else handler(alert)
            except Exception as e:
                self.logger.error(f"Alert handler error: {e}")
    
    # Background monitoring loops
    
    async def _system_metrics_loop(self):
        """Background task to collect system metrics"""
        while self.is_running:
            try:
                # CPU metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                self.set_gauge("system_cpu_percent", cpu_percent)
                
                # Memory metrics
                memory = psutil.virtual_memory()
                self.set_gauge("system_memory_percent", memory.percent)
                self.set_gauge("system_memory_available_bytes", memory.available)
                
                # Disk metrics
                disk = psutil.disk_usage('/')
                self.set_gauge("system_disk_percent", (disk.used / disk.total) * 100)
                
                # Network metrics
                net_io = psutil.net_io_counters()
                self.set_gauge("system_network_bytes_sent", net_io.bytes_sent)
                self.set_gauge("system_network_bytes_recv", net_io.bytes_recv)
                
                # Check for high resource usage
                if cpu_percent > 80:
                    await self.create_alert(
                        AlertSeverity.HIGH,
                        f"High CPU usage: {cpu_percent:.1f}%",
                        "system",
                        "system_cpu_percent",
                        cpu_percent,
                        80
                    )
                
                if memory.percent > 85:
                    await self.create_alert(
                        AlertSeverity.HIGH,
                        f"High memory usage: {memory.percent:.1f}%",
                        "system",
                        "system_memory_percent",
                        memory.percent,
                        85
                    )
                
                await asyncio.sleep(self.system_metrics_interval)
                
            except Exception as e:
                self.logger.error(f"System metrics error: {e}")
                await asyncio.sleep(self.system_metrics_interval)
    
    async def _health_check_loop(self):
        """Background task to run health checks"""
        while self.is_running:
            try:
                await self.run_all_health_checks()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _alert_check_loop(self):
        """Background task to check for alert conditions"""
        while self.is_running:
            try:
                # Check for pattern-based alerts
                await self._check_error_patterns()
                await self._check_performance_degradation()
                await asyncio.sleep(self.alert_check_interval)
            except Exception as e:
                self.logger.error(f"Alert check error: {e}")
                await asyncio.sleep(self.alert_check_interval)
    
    async def _anomaly_detection_loop(self):
        """Background task for anomaly detection"""
        while self.is_running:
            try:
                await self.anomaly_detection.detect_anomalies(self.metrics)
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                self.logger.error(f"Anomaly detection error: {e}")
                await asyncio.sleep(60)
    
    async def _check_error_patterns(self):
        """Check for error patterns that might indicate issues"""
        current_time = datetime.now()
        
        # Check for error rate spikes
        for pattern, count in self.error_patterns.items():
            if count > 10:  # Threshold for error pattern
                await self.create_alert(
                    AlertSeverity.MEDIUM,
                    f"High error rate detected: {pattern} ({count} occurrences)",
                    "error_patterns",
                    "error_rate",
                    count,
                    10
                )
    
    async def _check_performance_degradation(self):
        """Check for performance degradation"""
        # Check average response times
        for endpoint, metrics in self.request_metrics.items():
            if len(metrics) > 10:
                recent_times = [m.value for m in list(metrics)[-10:]]
                avg_time = np.mean(recent_times)
                
                if avg_time > 2.0:  # 2 seconds threshold
                    await self.create_alert(
                        AlertSeverity.MEDIUM,
                        f"Performance degradation detected: {endpoint} avg response time {avg_time:.2f}s",
                        "performance",
                        "response_time",
                        avg_time,
                        2.0
                    )
    
    # API for external access
    
    def get_metrics(self, name: str = None) -> Dict[str, List[Metric]]:
        """Get metrics data"""
        if name:
            return {name: list(self.metrics.get(name, []))}
        return {k: list(v) for k, v in self.metrics.items()}
    
    def get_alerts(self, resolved: bool = None) -> List[Alert]:
        """Get alerts"""
        if resolved is None:
            return self.alerts
        return [alert for alert in self.alerts if alert.resolved == resolved]
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status"""
        all_healthy = all(check.status == "healthy" for check in self.health_checks.values())
        return {
            "overall_status": "healthy" if all_healthy else "unhealthy",
            "checks": {name: check.status for name, check in self.health_checks.items()},
            "details": self.health_checks
        }
    
    def get_circuit_breaker_status(self) -> Dict[str, CircuitBreaker]:
        """Get circuit breaker status"""
        return self.circuit_breakers


class AnomalyDetector:
    """
    Simple anomaly detection using statistical methods
    """
    
    def __init__(self):
        self.baselines = {}
        self.logger = logging.getLogger(__name__)
    
    async def detect_anomalies(self, metrics: Dict[str, deque]):
        """Detect anomalies in metrics"""
        for metric_name, metric_values in metrics.items():
            if len(metric_values) < 10:
                continue
            
            values = [m.value for m in metric_values if isinstance(m.value, (int, float))]
            if len(values) < 10:
                continue
            
            # Calculate baseline if not exists
            if metric_name not in self.baselines:
                self.baselines[metric_name] = {
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'last_updated': datetime.now()
                }
                continue
            
            # Check for anomalies
            baseline = self.baselines[metric_name]
            recent_values = values[-5:]  # Last 5 values
            
            for value in recent_values:
                z_score = abs(value - baseline['mean']) / (baseline['std'] + 1e-8)
                if z_score > 3:  # 3 standard deviations
                    self.logger.warning(f"Anomaly detected in {metric_name}: {value} (z-score: {z_score:.2f})")
            
            # Update baseline periodically
            if datetime.now() - baseline['last_updated'] > timedelta(hours=1):
                baseline['mean'] = np.mean(values)
                baseline['std'] = np.std(values)
                baseline['last_updated'] = datetime.now()


# Global instance
observability = ObservabilitySystem()


# Decorators for easy integration

def monitor_performance(metric_name: str = None):
    """Decorator to monitor function performance"""
    def decorator(func):
        name = metric_name or f"{func.__module__}.{func.__name__}"
        
        async def async_wrapper(*args, **kwargs):
            async with observability.time_operation(name):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                observability.record_metric(
                    f"{name}_duration_seconds",
                    duration,
                    MetricType.TIMER,
                    unit="seconds"
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                observability.record_metric(
                    f"{name}_duration_seconds",
                    duration,
                    MetricType.TIMER,
                    {"status": "error"},
                    "seconds"
                )
                observability.increment_counter(f"{name}_errors_total")
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def monitor_errors(component: str = None):
    """Decorator to monitor function errors"""
    def decorator(func):
        comp = component or func.__module__
        
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                observability.increment_counter(f"{comp}_errors_total", labels={"error_type": type(e).__name__})
                observability.error_patterns[f"{comp}:{type(e).__name__}"] += 1
                raise
        
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                observability.increment_counter(f"{comp}_errors_total", labels={"error_type": type(e).__name__})
                observability.error_patterns[f"{comp}:{type(e).__name__}"] += 1
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# Usage examples for integration
if __name__ == "__main__":
    async def example_usage():
        # Initialize observability
        await observability.initialize()
        
        # Register health checks
        observability.register_health_check("database", lambda: True)
        observability.register_health_check("redis", lambda: True)
        
        # Register circuit breaker
        observability.register_circuit_breaker("external_api", failure_threshold=3)
        
        # Record metrics
        observability.set_gauge("active_users", 150)
        observability.increment_counter("api_requests_total")
        
        # Add alert handler
        def alert_handler(alert):
            print(f"ALERT: {alert.severity.value} - {alert.message}")
        
        observability.add_alert_handler(alert_handler)
        
        # Use decorators
        @monitor_performance("example_function")
        @monitor_errors("example_component")
        async def example_function():
            await asyncio.sleep(0.1)
            return "result"
        
        result = await example_function()
        print(f"Result: {result}")
        
        # Check health
        health = observability.get_health_status()
        print(f"Health: {health}")
        
        # Wait a bit to see metrics
        await asyncio.sleep(2)
        
        # Cleanup
        await observability.shutdown()
    
    asyncio.run(example_usage())