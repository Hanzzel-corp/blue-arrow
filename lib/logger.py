#!/usr/bin/env python3
"""
Structured logging for Python modules.
Provides centralized logging with JSON formatting and configuration.
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from lib.config import get_config


class StructuredLogger:
    """Structured logger with JSON formatting."""
    
    def __init__(self, module_id: str):
        self.module_id = module_id
        self.config = get_config()
        self.log_config = self.config.get_logging_config()
        self.log_level = self._get_log_level_number(self.log_config.get('level', 'info'))
        
        # Setup Python logging
        self._setup_logging()
    
    def _get_log_level_number(self, level: str) -> int:
        """Convert log level string to number."""
        levels = {
            'error': 0,
            'warn': 1,
            'info': 2,
            'debug': 3,
            'trace': 4
        }
        return levels.get(level.lower(), 2)
    
    def _should_log(self, level: str) -> bool:
        """Check if message should be logged based on level."""
        return self._get_log_level_number(level) <= self.log_level
    
    def _setup_logging(self) -> None:
        """Setup Python logging configuration."""
        # Create logs directory if it doesn't exist
        logs_dir = Path(self.config.get('runtime.logs_dir', 'logs'))
        logs_dir.mkdir(exist_ok=True)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Console handler
        if self.log_config.get('console', True):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            
            if self.log_config.get('structured', True):
                formatter = StructuredFormatter(self.module_id)
            else:
                formatter = SimpleFormatter(self.module_id)
            
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # File handler
        if self.log_config.get('file', True):
            log_file = logs_dir / f"{self.module_id}.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            
            if self.log_config.get('structured', True):
                formatter = StructuredFormatter(self.module_id)
            else:
                formatter = SimpleFormatter(self.module_id)
            
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
    
    def _format_message(self, level: str, message: str, meta: Optional[Dict[str, Any]] = None) -> str:
        """Format log message."""
        meta = meta or {}
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        log_entry = {
            'timestamp': timestamp,
            'level': level.upper(),
            'module': self.module_id,
            'message': message,
            **meta
        }
        
        if self.log_config.get('structured', True):
            return json.dumps(log_entry)
        else:
            meta_str = f" {json.dumps(meta)}" if meta else ""
            return f"[{timestamp}] {level.upper()} [{self.module_id}] {message}{meta_str}"
    
    def _log(self, level: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Log a message at the specified level."""
        if not self._should_log(level):
            return
        
        formatted_message = self._format_message(level, message, meta)
        
        # Use Python's logging system
        log_level = getattr(logging, level.upper(), logging.INFO)
        logging.log(log_level, formatted_message)
    
    def error(self, message: str, **meta) -> None:
        """Log error message."""
        self._log('error', message, meta)
    
    def warn(self, message: str, **meta) -> None:
        """Log warning message."""
        self._log('warn', message, meta)
    
    def info(self, message: str, **meta) -> None:
        """Log info message."""
        self._log('info', message, meta)
    
    def debug(self, message: str, **meta) -> None:
        """Log debug message."""
        self._log('debug', message, meta)
    
    def trace(self, message: str, **meta) -> None:
        """Log trace message."""
        self._log('trace', message, meta)
    
    # Specialized logging methods
    def message_routing(self, from_module: str, from_port: str, to_module: str, 
                       to_port: str, message_id: str) -> None:
        """Log message routing."""
        self.debug("Message routed", 
                  event_type="message_routing",
                  from_module=from_module,
                  from_port=from_port,
                  to_module=to_module,
                  to_port=to_port,
                  message_id=message_id)
    
    def task_started(self, task_id: str, action: str, module: str) -> None:
        """Log task start."""
        self.info("Task started",
                 event_type="task_started",
                 task_id=task_id,
                 action=action,
                 module=module)
    
    def task_completed(self, task_id: str, action: str, duration: float, 
                      result: Any) -> None:
        """Log task completion."""
        self.info("Task completed",
                 event_type="task_completed",
                 task_id=task_id,
                 action=action,
                 duration_ms=duration,
                 result_type=type(result).__name__)
    
    def task_failed(self, task_id: str, action: str, duration: float, 
                   error: Exception) -> None:
        """Log task failure."""
        self.error("Task failed",
                  event_type="task_failed",
                  task_id=task_id,
                  action=action,
                  duration_ms=duration,
                  error=str(error),
                  error_type=type(error).__name__)
    
    def performance(self, operation: str, duration: float, **metadata) -> None:
        """Log performance metric."""
        self.debug("Performance metric",
                  event_type="performance",
                  operation=operation,
                  duration_ms=duration,
                  **metadata)
    
    def security_event(self, event_type: str, **details) -> None:
        """Log security event."""
        self.warn("Security event",
                 event_type="security",
                 security_event_type=event_type,
                 **details)
    
    def memory_operation(self, operation: str, key: str, **metadata) -> None:
        """Log memory operation."""
        self.debug("Memory operation",
                  event_type="memory_operation",
                  operation=operation,
                  key=key,
                  **metadata)
    
    def worker_event(self, event_type: str, **details) -> None:
        """Log worker-specific event."""
        self.info(f"Worker {event_type}",
                 event_type=f"worker_{event_type}",
                 **details)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def __init__(self, module_id: str):
        super().__init__()
        self.module_id = module_id
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'module': self.module_id,
            'message': record.getMessage(),
            'logger': record.name
        }
        
        # Add extra fields if present
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 
                              'pathname', 'filename', 'module', 'lineno', 
                              'funcName', 'created', 'msecs', 'relativeCreated', 
                              'thread', 'threadName', 'processName', 'process',
                              'getMessage', 'exc_info', 'exc_text', 'stack_info']:
                    log_entry[key] = value
        
        return json.dumps(log_entry)


class SimpleFormatter(logging.Formatter):
    """Simple formatter for development logging."""
    
    def __init__(self, module_id: str):
        super().__init__()
        self.module_id = module_id
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record in simple format."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        message = record.getMessage()
        
        # Add extra fields as JSON if present
        extra_fields = {}
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 
                              'pathname', 'filename', 'module', 'lineno', 
                              'funcName', 'created', 'msecs', 'relativeCreated', 
                              'thread', 'threadName', 'processName', 'process',
                              'getMessage', 'exc_info', 'exc_text', 'stack_info']:
                    extra_fields[key] = value
        
        extra_str = f" {json.dumps(extra_fields)}" if extra_fields else ""
        return f"[{timestamp}] {record.levelname} [{self.module_id}] {message}{extra_str}"


# Logger registry
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(module_id: str) -> StructuredLogger:
    """Get or create a logger for the specified module."""
    if module_id not in _loggers:
        _loggers[module_id] = StructuredLogger(module_id)
    return _loggers[module_id]


# Context manager for performance timing
class Timer:
    """Context manager for timing operations."""
    
    def __init__(self, logger: StructuredLogger, operation: str, **metadata):
        self.logger = logger
        self.operation = operation
        self.metadata = metadata
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self.start_time) * 1000  # Convert to ms
        
        if exc_type is not None:
            self.logger.error(f"Operation failed: {self.operation}",
                           operation=self.operation,
                           duration_ms=duration,
                           error=str(exc_val),
                           **self.metadata)
        else:
            self.logger.performance(self.operation, duration, **self.metadata)


def timer(logger: StructuredLogger, operation: str, **metadata) -> Timer:
    """Create a timer context manager."""
    return Timer(logger, operation, **metadata)


# Decorator for function timing
def log_performance(logger: StructuredLogger, operation: str = None):
    """Decorator to log function performance."""
    def decorator(func):
        op_name = operation or f"{func.__module__}.{func.__name__}"
        
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                logger.performance(op_name, duration, 
                                 function=func.__name__,
                                 args_count=len(args),
                                 kwargs_keys=list(kwargs.keys()))
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(f"Function failed: {op_name}",
                          operation=op_name,
                          duration_ms=duration,
                          error=str(e),
                          function=func.__name__)
                raise
        
        return wrapper
    return decorator


# Default logger instance
default_logger = get_logger("python_worker")
