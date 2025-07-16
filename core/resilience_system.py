"""
Advanced Resilience System with Circuit Breaker Pattern
Prevents cascading failures and ensures system stability
"""

import asyncio
import functools
import logging
import random
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Union, Tuple
import aiohttp
import redis.asyncio as redis
from dataclasses import asdict

from .observability_system import observability, MetricType, AlertSeverity


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing, blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class RetryStrategy(Enum):
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIBONACCI = "fibonacci"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    backoff_factor: float = 2.0
    jitter: bool = True
    retry_exceptions: Tuple[type, ...] = (Exception,)
    stop_exceptions: Tuple[type, ...] = ()


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: type = Exception
    half_open_max_calls: int = 3
    sliding_window_size: int = 100
    minimum_throughput: int = 10


@dataclass
class BulkheadConfig:
    max_concurrent_calls: int = 10
    max_queue_size: int = 100
    timeout: float = 30.0


@dataclass
class CallResult:
    success: bool
    duration: float
    exception: Optional[Exception] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CircuitBreakerStats:
    name: str
    state: CircuitState
    failure_count: int
    success_count: int
    total_calls: int
    last_failure_time: Optional[datetime]
    last_success_time: Optional[datetime]
    recovery_started: Optional[datetime]
    half_open_calls: int


class CircuitBreaker:
    """
    Circuit breaker implementation with sliding window and advanced recovery
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        self.last_failure_time = None
        self.last_success_time = None
        self.recovery_started = None
        
        # Sliding window for call history
        self.call_history = deque(maxlen=config.sliding_window_size)
        
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        
        # Check if circuit is open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.recovery_started = datetime.now()
                self.logger.info(f"Circuit breaker {self.name} entering HALF_OPEN state")
            else:
                self._record_blocked_call()
                raise CircuitBreakerOpenException(f"Circuit breaker {self.name} is OPEN")
        
        # Check half-open state limits
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                self._record_blocked_call()
                raise CircuitBreakerOpenException(f"Circuit breaker {self.name} HALF_OPEN max calls reached")
            self.half_open_calls += 1
        
        # Execute the function
        start_time = time.time()
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Record success
            duration = time.time() - start_time
            self._record_success(duration)
            
            return result
            
        except Exception as e:
            # Record failure
            duration = time.time() - start_time
            self._record_failure(duration, e)
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset"""
        if self.last_failure_time is None:
            return True
        
        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure.total_seconds() >= self.config.recovery_timeout
    
    def _record_success(self, duration: float):
        """Record successful call"""
        call_result = CallResult(success=True, duration=duration)
        self.call_history.append(call_result)
        
        self.success_count += 1
        self.last_success_time = datetime.now()
        
        # State transitions
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.logger.info(f"Circuit breaker {self.name} recovered to CLOSED state")
        
        # Record metrics
        observability.record_metric(
            f"circuit_breaker_{self.name}_success_rate",
            self._calculate_success_rate(),
            MetricType.GAUGE
        )
    
    def _record_failure(self, duration: float, exception: Exception):
        """Record failed call"""
        call_result = CallResult(success=False, duration=duration, exception=exception)
        self.call_history.append(call_result)
        
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        # Check if we should trip the circuit
        if self._should_trip_circuit():
            self.state = CircuitState.OPEN
            self.logger.warning(f"Circuit breaker {self.name} tripped to OPEN state")
            
            # Create alert
            asyncio.create_task(self._create_circuit_breaker_alert())
        
        # Record metrics
        observability.increment_counter(
            f"circuit_breaker_{self.name}_failures_total",
            labels={"exception": type(exception).__name__}
        )
    
    def _record_blocked_call(self):
        """Record blocked call due to open circuit"""
        observability.increment_counter(
            f"circuit_breaker_{self.name}_blocked_calls_total"
        )
    
    def _should_trip_circuit(self) -> bool:
        """Check if circuit should be tripped"""
        if len(self.call_history) < self.config.minimum_throughput:
            return False
        
        recent_calls = list(self.call_history)[-self.config.minimum_throughput:]
        failure_rate = sum(1 for call in recent_calls if not call.success) / len(recent_calls)
        
        return failure_rate >= (self.config.failure_threshold / len(recent_calls))
    
    def _calculate_success_rate(self) -> float:
        """Calculate current success rate"""
        if not self.call_history:
            return 1.0
        
        successful_calls = sum(1 for call in self.call_history if call.success)
        return successful_calls / len(self.call_history)
    
    async def _create_circuit_breaker_alert(self):
        """Create alert for circuit breaker trip"""
        await observability.create_alert(
            AlertSeverity.HIGH,
            f"Circuit breaker {self.name} tripped to OPEN state",
            "resilience",
            f"circuit_breaker_{self.name}_state",
            1,
            0,
            {
                "failure_count": self.failure_count,
                "success_rate": self._calculate_success_rate()
            }
        )
    
    def get_stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics"""
        return CircuitBreakerStats(
            name=self.name,
            state=self.state,
            failure_count=self.failure_count,
            success_count=self.success_count,
            total_calls=len(self.call_history),
            last_failure_time=self.last_failure_time,
            last_success_time=self.last_success_time,
            recovery_started=self.recovery_started,
            half_open_calls=self.half_open_calls
        )


class Bulkhead:
    """
    Bulkhead pattern implementation for resource isolation
    """
    
    def __init__(self, name: str, config: BulkheadConfig):
        self.name = name
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_concurrent_calls)
        self.queue = asyncio.Queue(maxsize=config.max_queue_size)
        self.active_calls = 0
        self.total_calls = 0
        self.rejected_calls = 0
        
        self.logger = logging.getLogger(f"{__name__}.bulkhead.{name}")
    
    async def execute(self, func: Callable, *args, **kwargs):
        """Execute function with bulkhead protection"""
        
        # Check if we can acquire semaphore
        if self.semaphore.locked():
            self.rejected_calls += 1
            observability.increment_counter(
                f"bulkhead_{self.name}_rejected_calls_total"
            )
            raise BulkheadRejectedException(f"Bulkhead {self.name} is full")
        
        # Execute with timeout and semaphore
        async with self.semaphore:
            self.active_calls += 1
            self.total_calls += 1
            
            try:
                result = await asyncio.wait_for(
                    self._execute_function(func, *args, **kwargs),
                    timeout=self.config.timeout
                )
                return result
            finally:
                self.active_calls -= 1
    
    async def _execute_function(self, func: Callable, *args, **kwargs):
        """Execute the actual function"""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bulkhead statistics"""
        return {
            "name": self.name,
            "active_calls": self.active_calls,
            "total_calls": self.total_calls,
            "rejected_calls": self.rejected_calls,
            "available_slots": self.config.max_concurrent_calls - self.active_calls
        }


class RetryManager:
    """
    Advanced retry manager with multiple strategies
    """
    
    def __init__(self, name: str, config: RetryConfig):
        self.name = name
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.retry.{name}")
    
    async def execute(self, func: Callable, *args, **kwargs):
        """Execute function with retry logic"""
        last_exception = None
        
        for attempt in range(self.config.max_attempts):
            try:
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                
                # Success - record metrics
                if attempt > 0:
                    observability.increment_counter(
                        f"retry_{self.name}_success_after_retry_total",
                        labels={"attempt": str(attempt + 1)}
                    )
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if we should stop retrying
                if any(isinstance(e, stop_ex) for stop_ex in self.config.stop_exceptions):
                    self.logger.info(f"Retry {self.name} stopped due to stop exception: {type(e).__name__}")
                    break
                
                # Check if exception is retryable
                if not any(isinstance(e, retry_ex) for retry_ex in self.config.retry_exceptions):
                    self.logger.info(f"Retry {self.name} stopped due to non-retryable exception: {type(e).__name__}")
                    break
                
                # Don't retry on last attempt
                if attempt == self.config.max_attempts - 1:
                    break
                
                # Calculate delay
                delay = self._calculate_delay(attempt)
                
                self.logger.warning(f"Retry {self.name} attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s")
                
                # Record retry metric
                observability.increment_counter(
                    f"retry_{self.name}_attempts_total",
                    labels={"attempt": str(attempt + 1), "exception": type(e).__name__}
                )
                
                await asyncio.sleep(delay)
        
        # All attempts failed
        observability.increment_counter(
            f"retry_{self.name}_exhausted_total",
            labels={"exception": type(last_exception).__name__}
        )
        
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt"""
        if self.config.strategy == RetryStrategy.FIXED:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (self.config.backoff_factor ** attempt)
        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.base_delay * (attempt + 1)
        elif self.config.strategy == RetryStrategy.FIBONACCI:
            delay = self.config.base_delay * self._fibonacci(attempt + 1)
        else:
            delay = self.config.base_delay
        
        # Apply max delay limit
        delay = min(delay, self.config.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.config.jitter:
            delay *= (0.5 + random.random() * 0.5)
        
        return delay
    
    def _fibonacci(self, n: int) -> int:
        """Calculate fibonacci number"""
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b


class ResilienceSystem:
    """
    Main resilience system coordinating all patterns
    """
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.bulkheads: Dict[str, Bulkhead] = {}
        self.retry_managers: Dict[str, RetryManager] = {}
        self.fallback_handlers: Dict[str, Callable] = {}
        
        self.logger = logging.getLogger(__name__)
    
    def register_circuit_breaker(self, name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
        """Register a circuit breaker"""
        config = config or CircuitBreakerConfig()
        circuit_breaker = CircuitBreaker(name, config)
        self.circuit_breakers[name] = circuit_breaker
        return circuit_breaker
    
    def register_bulkhead(self, name: str, config: BulkheadConfig = None) -> Bulkhead:
        """Register a bulkhead"""
        config = config or BulkheadConfig()
        bulkhead = Bulkhead(name, config)
        self.bulkheads[name] = bulkhead
        return bulkhead
    
    def register_retry_manager(self, name: str, config: RetryConfig = None) -> RetryManager:
        """Register a retry manager"""
        config = config or RetryConfig()
        retry_manager = RetryManager(name, config)
        self.retry_managers[name] = retry_manager
        return retry_manager
    
    def register_fallback(self, name: str, handler: Callable):
        """Register a fallback handler"""
        self.fallback_handlers[name] = handler
    
    async def execute_with_resilience(self, 
                                    func: Callable, 
                                    *args, 
                                    circuit_breaker: str = None,
                                    bulkhead: str = None,
                                    retry_manager: str = None,
                                    fallback: str = None,
                                    **kwargs):
        """
        Execute function with full resilience patterns
        """
        
        # Get components
        cb = self.circuit_breakers.get(circuit_breaker) if circuit_breaker else None
        bh = self.bulkheads.get(bulkhead) if bulkhead else None
        rm = self.retry_managers.get(retry_manager) if retry_manager else None
        fb = self.fallback_handlers.get(fallback) if fallback else None
        
        # Create execution wrapper
        async def execute():
            if bh:
                return await bh.execute(func, *args, **kwargs)
            elif asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        # Apply circuit breaker
        if cb:
            execute = lambda: cb.call(execute)
        
        # Apply retry logic
        if rm:
            execute = lambda: rm.execute(execute)
        
        # Execute with fallback
        try:
            return await execute()
        except Exception as e:
            if fb:
                self.logger.info(f"Executing fallback for {func.__name__}: {e}")
                return await fb(*args, **kwargs) if asyncio.iscoroutinefunction(fb) else fb(*args, **kwargs)
            raise
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get overall system statistics"""
        return {
            "circuit_breakers": {name: cb.get_stats() for name, cb in self.circuit_breakers.items()},
            "bulkheads": {name: bh.get_stats() for name, bh in self.bulkheads.items()},
            "retry_managers": list(self.retry_managers.keys()),
            "fallback_handlers": list(self.fallback_handlers.keys())
        }


# Custom exceptions
class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class BulkheadRejectedException(Exception):
    """Exception raised when bulkhead rejects request"""
    pass


class RetryExhaustedException(Exception):
    """Exception raised when all retry attempts are exhausted"""
    pass


# Global instance
resilience_system = ResilienceSystem()


# Decorators for easy integration

def circuit_breaker(name: str, config: CircuitBreakerConfig = None):
    """Decorator to add circuit breaker protection"""
    def decorator(func):
        cb = resilience_system.register_circuit_breaker(name, config)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(cb.call(func, *args, **kwargs))
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def bulkhead(name: str, config: BulkheadConfig = None):
    """Decorator to add bulkhead protection"""
    def decorator(func):
        bh = resilience_system.register_bulkhead(name, config)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await bh.execute(func, *args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(bh.execute(func, *args, **kwargs))
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def retry(name: str, config: RetryConfig = None):
    """Decorator to add retry logic"""
    def decorator(func):
        rm = resilience_system.register_retry_manager(name, config)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await rm.execute(func, *args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(rm.execute(func, *args, **kwargs))
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def resilient(circuit_breaker_name: str = None, 
              bulkhead_name: str = None, 
              retry_name: str = None,
              fallback_name: str = None):
    """Decorator to add full resilience patterns"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await resilience_system.execute_with_resilience(
                func, *args,
                circuit_breaker=circuit_breaker_name,
                bulkhead=bulkhead_name,
                retry_manager=retry_name,
                fallback=fallback_name,
                **kwargs
            )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(
                resilience_system.execute_with_resilience(
                    func, *args,
                    circuit_breaker=circuit_breaker_name,
                    bulkhead=bulkhead_name,
                    retry_manager=retry_name,
                    fallback=fallback_name,
                    **kwargs
                )
            )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# Usage examples
if __name__ == "__main__":
    async def example_usage():
        # Register components
        resilience_system.register_circuit_breaker("database", CircuitBreakerConfig(failure_threshold=3))
        resilience_system.register_bulkhead("api_calls", BulkheadConfig(max_concurrent_calls=5))
        resilience_system.register_retry_manager("external_service", RetryConfig(max_attempts=3))
        
        # Fallback function
        async def fallback_response():
            return "Service temporarily unavailable"
        
        resilience_system.register_fallback("service_fallback", fallback_response)
        
        # Example function
        @resilient(
            circuit_breaker_name="database",
            bulkhead_name="api_calls",
            retry_name="external_service",
            fallback_name="service_fallback"
        )
        async def external_api_call():
            # Simulate external API call
            await asyncio.sleep(0.1)
            if random.random() < 0.3:  # 30% failure rate
                raise Exception("API call failed")
            return "Success"
        
        # Test the resilient function
        for i in range(10):
            try:
                result = await external_api_call()
                print(f"Call {i+1}: {result}")
            except Exception as e:
                print(f"Call {i+1}: Failed - {e}")
        
        # Get system stats
        stats = resilience_system.get_system_stats()
        print(f"System stats: {stats}")
    
    asyncio.run(example_usage())