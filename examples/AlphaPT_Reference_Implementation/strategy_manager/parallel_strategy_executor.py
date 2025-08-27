"""Parallel strategy execution engine for high-performance processing."""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing as mp
from queue import Queue, Empty

from .base_strategy import BaseStrategy
from .signal_types import TradingSignal
from core.config.settings import Settings
from core.events import EventBusCore
from monitoring.performance_profiler import PerformanceProfiler, profile_performance

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Strategy execution performance metrics."""
    strategies_executed: int = 0
    total_execution_time_ms: float = 0.0
    signals_generated: int = 0
    market_data_processed: int = 0
    errors: int = 0
    timeouts: int = 0
    queue_depth: int = 0
    
    @property
    def average_execution_time_ms(self) -> float:
        """Calculate average execution time per strategy."""
        return self.total_execution_time_ms / max(self.strategies_executed, 1)
    
    @property
    def processing_rate_per_sec(self) -> float:
        """Calculate strategy processing rate per second."""
        if self.total_execution_time_ms > 0:
            return (self.strategies_executed * 1000) / self.total_execution_time_ms
        return 0.0


@dataclass
class StrategyWorkItem:
    """Work item for strategy execution."""
    strategy_name: str
    instrument_token: int
    market_data: Dict[str, Any]
    timestamp: datetime
    priority: int = 0  # Higher values = higher priority
    retry_count: int = 0
    max_retries: int = 3


class ParallelStrategyExecutor:
    """High-performance parallel strategy execution engine."""
    
    def __init__(self, settings: Settings, event_bus: EventBusCore, profiler: Optional[PerformanceProfiler] = None):
        self.settings = settings
        self.event_bus = event_bus
        self.profiler = profiler
        
        # Configuration
        self.max_workers = getattr(settings, 'strategy_max_workers', mp.cpu_count())
        self.enable_multiprocessing = getattr(settings, 'strategy_enable_multiprocessing', False)
        self.execution_timeout = getattr(settings, 'strategy_execution_timeout', 5.0)  # seconds
        self.queue_size = getattr(settings, 'strategy_queue_size', 10000)
        
        # Execution pools
        self.thread_pool: Optional[ThreadPoolExecutor] = None
        self.process_pool: Optional[ProcessPoolExecutor] = None
        
        # Work queues
        self.work_queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        self.priority_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=1000)
        self.result_queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        
        # Strategy management
        self.strategies: Dict[str, BaseStrategy] = {}
        self.strategy_workers: Dict[str, Set[asyncio.Task]] = defaultdict(set)
        self.strategy_load: Dict[str, int] = defaultdict(int)
        
        # Performance tracking
        self.metrics = ExecutionMetrics()
        self.execution_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.strategy_metrics: Dict[str, ExecutionMetrics] = defaultdict(ExecutionMetrics)
        
        # Execution state
        self.is_running = False
        self.worker_tasks: List[asyncio.Task] = []
        self.result_processor_task: Optional[asyncio.Task] = None
        
        # Thread safety
        self.metrics_lock = threading.Lock()
        
        # Circuit breaker pattern
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self.circuit_breaker_threshold = 5  # failures before opening circuit
        self.circuit_breaker_timeout = 60  # seconds before retry
    
    async def initialize(self) -> None:
        """Initialize the parallel execution engine."""
        try:
            logger.info("Initializing parallel strategy executor...")
            
            # Initialize thread pool
            self.thread_pool = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="strategy-exec"
            )
            
            # Initialize process pool if enabled
            if self.enable_multiprocessing:
                self.process_pool = ProcessPoolExecutor(
                    max_workers=min(self.max_workers, mp.cpu_count()),
                    mp_context=mp.get_context('spawn')
                )
                logger.info(f"Process pool initialized with {self.max_workers} workers")
            
            logger.info(f"Parallel strategy executor initialized with {self.max_workers} workers")
            
        except Exception as e:
            logger.error(f"Failed to initialize parallel strategy executor: {e}")
            raise
    
    async def start(self) -> None:
        """Start the parallel execution engine."""
        if self.is_running:
            return
        
        try:
            logger.info("Starting parallel strategy executor...")
            
            # Start worker tasks
            for i in range(self.max_workers):
                worker_task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
                self.worker_tasks.append(worker_task)
            
            # Start priority worker
            priority_worker = asyncio.create_task(self._priority_worker_loop())
            self.worker_tasks.append(priority_worker)
            
            # Start result processor
            self.result_processor_task = asyncio.create_task(self._result_processor_loop())
            
            self.is_running = True
            logger.info(f"Parallel strategy executor started with {len(self.worker_tasks)} workers")
            
        except Exception as e:
            logger.error(f"Failed to start parallel strategy executor: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the parallel execution engine."""
        try:
            logger.info("Stopping parallel strategy executor...")
            
            self.is_running = False
            
            # Cancel worker tasks
            for task in self.worker_tasks:
                task.cancel()
            
            # Wait for tasks to complete
            if self.worker_tasks:
                await asyncio.gather(*self.worker_tasks, return_exceptions=True)
            
            # Cancel result processor
            if self.result_processor_task:
                self.result_processor_task.cancel()
                try:
                    await self.result_processor_task
                except asyncio.CancelledError:
                    pass
            
            # Shutdown thread pools
            if self.thread_pool:
                self.thread_pool.shutdown(wait=True)
            
            if self.process_pool:
                self.process_pool.shutdown(wait=True)
            
            logger.info("Parallel strategy executor stopped")
            
        except Exception as e:
            logger.error(f"Error stopping parallel strategy executor: {e}")
    
    def register_strategy(self, strategy_name: str, strategy: BaseStrategy) -> None:
        """Register a strategy for parallel execution."""
        self.strategies[strategy_name] = strategy
        self.strategy_load[strategy_name] = 0
        self.circuit_breakers[strategy_name] = {
            'failures': 0,
            'last_failure': None,
            'state': 'closed'  # closed, open, half-open
        }
        logger.info(f"Registered strategy for parallel execution: {strategy_name}")
    
    def unregister_strategy(self, strategy_name: str) -> None:
        """Unregister a strategy from parallel execution."""
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]
            del self.strategy_load[strategy_name]
            del self.circuit_breakers[strategy_name]
            logger.info(f"Unregistered strategy: {strategy_name}")
    
    async def execute_strategy(
        self, 
        strategy_name: str, 
        instrument_token: int, 
        market_data: Dict[str, Any],
        priority: int = 0
    ) -> bool:
        """Queue strategy execution."""
        if not self.is_running:
            logger.warning("Executor not running, dropping execution request")
            return False
        
        if strategy_name not in self.strategies:
            logger.warning(f"Strategy not registered: {strategy_name}")
            return False
        
        # Check circuit breaker
        if not self._check_circuit_breaker(strategy_name):
            logger.warning(f"Circuit breaker open for strategy: {strategy_name}")
            return False
        
        try:
            work_item = StrategyWorkItem(
                strategy_name=strategy_name,
                instrument_token=instrument_token,
                market_data=market_data,
                timestamp=datetime.now(),
                priority=priority
            )
            
            # Route to appropriate queue based on priority
            if priority > 0:
                await self.priority_queue.put((priority, work_item))
            else:
                await self.work_queue.put(work_item)
            
            # Update queue depth metric
            self.metrics.queue_depth = self.work_queue.qsize() + self.priority_queue.qsize()
            
            return True
            
        except asyncio.QueueFull:
            logger.warning(f"Work queue full, dropping execution for {strategy_name}")
            return False
        except Exception as e:
            logger.error(f"Error queuing strategy execution: {e}")
            return False
    
    def _check_circuit_breaker(self, strategy_name: str) -> bool:
        """Check if strategy circuit breaker allows execution."""
        breaker = self.circuit_breakers.get(strategy_name, {})
        state = breaker.get('state', 'closed')
        
        if state == 'closed':
            return True
        elif state == 'open':
            # Check if timeout has passed
            last_failure = breaker.get('last_failure')
            if last_failure and (datetime.now() - last_failure).total_seconds() > self.circuit_breaker_timeout:
                # Move to half-open state
                breaker['state'] = 'half-open'
                return True
            return False
        elif state == 'half-open':
            return True
        
        return False
    
    def _update_circuit_breaker(self, strategy_name: str, success: bool) -> None:
        """Update circuit breaker state based on execution result."""
        if strategy_name not in self.circuit_breakers:
            return
        
        breaker = self.circuit_breakers[strategy_name]
        
        if success:
            if breaker['state'] == 'half-open':
                # Success in half-open state, close the circuit
                breaker['state'] = 'closed'
                breaker['failures'] = 0
        else:
            breaker['failures'] += 1
            breaker['last_failure'] = datetime.now()
            
            if breaker['failures'] >= self.circuit_breaker_threshold:
                breaker['state'] = 'open'
                logger.warning(f"Circuit breaker opened for strategy: {strategy_name}")
    
    async def _worker_loop(self, worker_id: str) -> None:
        """Main worker loop for processing strategy executions."""
        logger.info(f"Worker {worker_id} started")
        
        try:
            while self.is_running:
                try:
                    # Get work item with timeout
                    work_item = await asyncio.wait_for(
                        self.work_queue.get(), 
                        timeout=1.0
                    )
                    
                    # Execute strategy
                    await self._execute_work_item(work_item, worker_id)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error in worker {worker_id}: {e}")
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id} cancelled")
        except Exception as e:
            logger.error(f"Fatal error in worker {worker_id}: {e}")
    
    async def _priority_worker_loop(self) -> None:
        """Worker loop for high-priority strategy executions."""
        logger.info("Priority worker started")
        
        try:
            while self.is_running:
                try:
                    # Get priority work item
                    priority, work_item = await asyncio.wait_for(
                        self.priority_queue.get(),
                        timeout=1.0
                    )
                    
                    # Execute with higher priority
                    await self._execute_work_item(work_item, "priority-worker")
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error in priority worker: {e}")
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            logger.info("Priority worker cancelled")
        except Exception as e:
            logger.error(f"Fatal error in priority worker: {e}")
    
    @profile_performance("strategy_execution")
    async def _execute_work_item(self, work_item: StrategyWorkItem, worker_id: str) -> None:
        """Execute a strategy work item."""
        start_time = time.perf_counter()
        
        try:
            strategy = self.strategies[work_item.strategy_name]
            
            # Increment load counter
            self.strategy_load[work_item.strategy_name] += 1
            
            # Execute strategy in executor for CPU-intensive work
            if self.enable_multiprocessing and self.process_pool:
                # Use process pool for CPU-intensive strategies
                loop = asyncio.get_running_loop()
                signal = await loop.run_in_executor(
                    self.process_pool,
                    self._execute_strategy_sync,
                    strategy,
                    work_item.market_data
                )
            else:
                # Use thread pool for I/O-intensive strategies
                loop = asyncio.get_running_loop()
                signal = await loop.run_in_executor(
                    self.thread_pool,
                    self._execute_strategy_sync,
                    strategy,
                    work_item.market_data
                )
            
            # Record execution time
            execution_time = (time.perf_counter() - start_time) * 1000
            
            # Update metrics
            with self.metrics_lock:
                self.metrics.strategies_executed += 1
                self.metrics.total_execution_time_ms += execution_time
                self.metrics.market_data_processed += 1
                
                strategy_metrics = self.strategy_metrics[work_item.strategy_name]
                strategy_metrics.strategies_executed += 1
                strategy_metrics.total_execution_time_ms += execution_time
                
                if signal:
                    self.metrics.signals_generated += 1
                    strategy_metrics.signals_generated += 1
            
            # Record execution time for this strategy
            self.execution_times[work_item.strategy_name].append(execution_time)
            
            # Update circuit breaker
            self._update_circuit_breaker(work_item.strategy_name, True)
            
            # Queue result for processing
            if signal:
                await self.result_queue.put({
                    'signal': signal,
                    'strategy_name': work_item.strategy_name,
                    'execution_time_ms': execution_time,
                    'worker_id': worker_id
                })
            
            # Record performance metrics
            if self.profiler:
                self.profiler.record_timing(f"strategy_{work_item.strategy_name}", execution_time)
                self.profiler.increment_counter(f"strategy_executions_{work_item.strategy_name}")
            
        except asyncio.TimeoutError:
            logger.warning(f"Strategy execution timeout: {work_item.strategy_name}")
            with self.metrics_lock:
                self.metrics.timeouts += 1
                self.strategy_metrics[work_item.strategy_name].timeouts += 1
            
            self._update_circuit_breaker(work_item.strategy_name, False)
            
        except Exception as e:
            logger.error(f"Error executing strategy {work_item.strategy_name}: {e}")
            
            with self.metrics_lock:
                self.metrics.errors += 1
                self.strategy_metrics[work_item.strategy_name].errors += 1
            
            self._update_circuit_breaker(work_item.strategy_name, False)
            
            # Retry logic
            if work_item.retry_count < work_item.max_retries:
                work_item.retry_count += 1
                await asyncio.sleep(0.1 * work_item.retry_count)  # Exponential backoff
                await self.work_queue.put(work_item)
        
        finally:
            # Decrement load counter
            self.strategy_load[work_item.strategy_name] -= 1
    
    def _execute_strategy_sync(self, strategy: BaseStrategy, market_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Synchronous strategy execution (for executor)."""
        try:
            # This would typically be a synchronous version of the strategy
            # For now, we'll simulate the execution
            return asyncio.run(strategy.process_market_data(market_data))
        except Exception as e:
            logger.error(f"Sync strategy execution error: {e}")
            return None
    
    async def _result_processor_loop(self) -> None:
        """Process strategy execution results."""
        logger.info("Result processor started")
        
        try:
            while self.is_running:
                try:
                    result = await asyncio.wait_for(
                        self.result_queue.get(),
                        timeout=1.0
                    )
                    
                    # Process the result
                    await self._process_strategy_result(result)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing result: {e}")
                    
        except asyncio.CancelledError:
            logger.info("Result processor cancelled")
        except Exception as e:
            logger.error(f"Fatal error in result processor: {e}")
    
    async def _process_strategy_result(self, result: Dict[str, Any]) -> None:
        """Process a strategy execution result."""
        try:
            signal = result['signal']
            strategy_name = result['strategy_name']
            execution_time = result['execution_time_ms']
            
            logger.debug(f"Processing signal from {strategy_name} (exec time: {execution_time:.2f}ms)")
            
            # Route signal through event bus
            signal_data = signal.to_dict()
            await self.event_bus.publish(f"trading.signal.{strategy_name}", signal_data)
            
        except Exception as e:
            logger.error(f"Error processing strategy result: {e}")
    
    def get_execution_metrics(self) -> Dict[str, Any]:
        """Get execution performance metrics."""
        with self.metrics_lock:
            queue_depth = self.work_queue.qsize() + self.priority_queue.qsize()
            
            return {
                'global_metrics': {
                    'strategies_executed': self.metrics.strategies_executed,
                    'average_execution_time_ms': self.metrics.average_execution_time_ms,
                    'processing_rate_per_sec': self.metrics.processing_rate_per_sec,
                    'signals_generated': self.metrics.signals_generated,
                    'market_data_processed': self.metrics.market_data_processed,
                    'errors': self.metrics.errors,
                    'timeouts': self.metrics.timeouts,
                    'queue_depth': queue_depth,
                },
                'strategy_metrics': {
                    name: {
                        'executed': metrics.strategies_executed,
                        'avg_time_ms': metrics.average_execution_time_ms,
                        'processing_rate': metrics.processing_rate_per_sec,
                        'signals': metrics.signals_generated,
                        'errors': metrics.errors,
                        'timeouts': metrics.timeouts,
                        'current_load': self.strategy_load.get(name, 0),
                    }
                    for name, metrics in self.strategy_metrics.items()
                },
                'circuit_breakers': {
                    name: {
                        'state': breaker['state'],
                        'failures': breaker['failures'],
                        'last_failure': breaker['last_failure'].isoformat() if breaker['last_failure'] else None
                    }
                    for name, breaker in self.circuit_breakers.items()
                },
                'execution_time_percentiles': self._calculate_execution_percentiles(),
            }
    
    def _calculate_execution_percentiles(self) -> Dict[str, Dict[str, float]]:
        """Calculate execution time percentiles for each strategy."""
        percentiles = {}
        
        for strategy_name, times in self.execution_times.items():
            if times:
                sorted_times = sorted(times)
                count = len(sorted_times)
                
                percentiles[strategy_name] = {
                    'p50': sorted_times[int(count * 0.5)],
                    'p90': sorted_times[int(count * 0.9)],
                    'p95': sorted_times[int(count * 0.95)],
                    'p99': sorted_times[int(count * 0.99)],
                    'min': sorted_times[0],
                    'max': sorted_times[-1],
                }
        
        return percentiles
    
    def get_strategy_load_balancing_info(self) -> Dict[str, Any]:
        """Get information for load balancing decisions."""
        return {
            'strategy_load': dict(self.strategy_load),
            'queue_sizes': {
                'work_queue': self.work_queue.qsize(),
                'priority_queue': self.priority_queue.qsize(),
                'result_queue': self.result_queue.qsize(),
            },
            'worker_count': len(self.worker_tasks),
            'active_workers': sum(1 for task in self.worker_tasks if not task.done()),
            'circuit_breaker_states': {
                name: breaker['state'] 
                for name, breaker in self.circuit_breakers.items()
            }
        }
    
    async def adjust_worker_count(self, new_count: int) -> bool:
        """Dynamically adjust the number of worker tasks."""
        try:
            current_count = len(self.worker_tasks)
            
            if new_count > current_count:
                # Add workers
                for i in range(current_count, new_count):
                    worker_task = asyncio.create_task(self._worker_loop(f"dynamic-worker-{i}"))
                    self.worker_tasks.append(worker_task)
                
                logger.info(f"Increased workers from {current_count} to {new_count}")
                
            elif new_count < current_count:
                # Remove workers (cancel excess tasks)
                workers_to_remove = self.worker_tasks[new_count:]
                self.worker_tasks = self.worker_tasks[:new_count]
                
                for task in workers_to_remove:
                    task.cancel()
                
                logger.info(f"Decreased workers from {current_count} to {new_count}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error adjusting worker count: {e}")
            return False