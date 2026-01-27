import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

MAX_EXPERIMENT_LOGS = 3

# Separator formatting constants
SEP_WIDTH = 50
SEP_CHAR = "-"

# Thread lock for atomic log groups (sep + message + bottom)
_log_lock = threading.Lock()

# Logging level mapping
log_dict = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class ShortFormatter(logging.Formatter):
    """
    Custom formatter for short logs.
    Format: time [TYPE] [name]: msg
    - Uses context_name if set via get_named_logger(), shows both context and module source
    - Strips __ from module names
    - Uses context_module_name from filter when available
    """
    def format(self, record):
        # Get context and module names in short forms from filter
        context_name = getattr(record, 'context_name', None)
        if context_name is not None:
            context_name = context_name.split('.')[-1].strip('_')
        
        module_name = getattr(record, 'context_module_name', None)
        if module_name is not None:
            module_name = module_name.split('.')[-1].strip('_')
        else:
            module_name = record.name.split('.')[-1].strip('_')
        
        # Build display name
        if (context_name is not None and module_name and 
            context_name not in module_name):
            name = f"{context_name}:{module_name}"
        elif context_name is not None:
            name = context_name
        else:
            name = module_name
        
        # Format timestamp
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        
        # Format level (shorter)
        level = record.levelname
        
        # Build the message
        msg = record.getMessage()
        return f"{time_str} [{level}] [{name}]: {msg}"


class LongFormatter(logging.Formatter):
    """
    Custom formatter for full logs output.
    Format: time [TYPE] [process] [name]: msg
    - Uses context_name if set via get_named_logger(), shows both context and module source
    """
    def format(self, record):
        # Format timestamp
        time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        
        # Format level
        level = record.levelname.ljust(8)
        
        context_name = getattr(record, 'context_name', None)
        module_name = getattr(record, 'context_module_name', None)
        if module_name is not None:
            module_name = module_name.strip('_')
        else:
            module_name = record.name.strip('_')
        
        # Build display name
        if (context_name is not None and module_name and 
            context_name not in module_name):
            name = f"{context_name}:{module_name}"
        elif context_name is not None:
            name = context_name
        else:
            name = module_name
        
        # Build the message
        msg = record.getMessage()
        return f"{time_str} [{level}] [{record.process}] [{name}]: {msg}"


class ContextNameFilter(logging.Filter):
    """
    Filter that adds a context_name and module_name attribute to log records.
    Used by get_named_logger() to provide custom logger names.
    """
    def __init__(self, context_name: str, module_name: str = None):
        super().__init__()
        self.context_name = context_name
        self.module_name = module_name
    
    def filter(self, record):
        record.context_name = self.context_name
        record.context_module_name = self.module_name
        return True


def _has_effective_handlers(logger):
    """
    Check if a logger has any effective handlers (including inherited ones).
    Returns True if the logger or any of its parents have handlers configured.
    """
    current = logger
    while current:
        if current.handlers:
            return True
        if not current.propagate:
            break
        current = current.parent
    return False


def _add_context_filter(logger, context_name: str, module_name: str = None):
    """
    Add a ContextNameFilter to the logger if not already present.
    
    Args:
        logger: The logger to add the filter to
        context_name: The context name to use in log output
        module_name: The module name to use in log output
    """
    for f in logger.filters:
        if isinstance(f, ContextNameFilter) and f.context_name == context_name:
            return  # Already has this filter
    logger.addFilter(ContextNameFilter(context_name, module_name))


def _ensure_console_handler(logger, formatter: str = "short"):
    """
    Ensure there's at least a console handler for output.
    Adds handler to ROOT logger so all loggers benefit and propagation works.
    Called when no handlers exist to guarantee logs are captured.
    
    Args:
        logger: The logger that triggered this (unused, handler goes to root)
        formatter: Format style - "short" or "long"
    """
    root = logging.getLogger()
    # Only add if root doesn't already have handlers
    if not root.handlers:
        formatter_cls = LongFormatter if formatter == "long" else ShortFormatter
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter_cls())
        root.addHandler(console_handler)
        root.setLevel(logging.INFO)


def get_named_logger(
        context_name: str, module_name: str = None, formatter: str = "short",
        level: str = "info") -> logging.Logger:
    """
    Get a logger with a custom context name displayed in log output.
    
    This allows logs to show a meaningful name like [myLogger] instead of
    the module path [utils.core.csv_writter].
    
    When no handlers are configured (e.g., subprocess),
    automatically adds a console handler to ensure logs are captured.
    
    Args:
        context_name: The name to display in log output (e.g., "myLogger")
        module_name: Optional module name for the underlying logger. 
                     If None, uses context_name as the logger name.
        formatter: Format style - "short" or "long" (default "short")
        level: Logging level (default logging.INFO)
    
    Returns:
        A standard logging.Logger that displays context_name in formatted output.
    
    Example:
        from util.core.setup_logging import get_named_logger
        logger = get_named_logger("myLogger", __name__)
        logger.info("Training started")  # Output: 12:00:00 [INFO] [myLogger]: Training started
        logger.info("Debug info", log=verbose)  # Only logs if verbose=True
        
        # Use long format with PID and full timestamp
        logger = get_named_logger("myLogger", __name__, formatter="long")
    """
    # Use context_name as part of logger name to ensure unique loggers per context
    # This prevents filter collision when multiple instances use the same module
    logger_name = context_name if context_name else module_name
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_dict.get(level, logging.INFO))
    
    # Add context name filter if not already present
    _add_context_filter(logger, context_name, module_name)
    
    # If no handlers are configured, add a console handler for reliable output
    # This ensures logs are captured in subprocess/Iridis environments
    if not _has_effective_handlers(logger):
        _ensure_console_handler(logger, formatter)
    
    return logger


def _section_log(self, level, msg, args, exc_info=None, extra=None, 
                 stack_info=False, stacklevel=1, **kwargs):
    """
    Custom _log method that supports sep/bottom kwargs for section formatting.
    Uses a thread lock to ensure atomic output of separator groups.
    
    Usage:
        logger.info("Episode 0 started", sep=True)           # Separator line above message
        logger.info("Episode complete", bottom=True)         # Short separator below message
        logger.info("Major section", sep=True, bottom=True)  # Both above and below
        logger.info("Regular message")                       # Normal log line
        logger.info("Conditional msg", log=some_flag)        # Only logs if log=True or level > INFO
    """
    # Extract our custom kwargs
    sep = kwargs.pop('sep', False)
    bottom = kwargs.pop('bottom', False)
    n_dashes = kwargs.pop('n_dashes', SEP_WIDTH)
    should_log = kwargs.pop('log', None)
    
    # Treat log=None as "use default" (log it)
    if should_log is None:
        should_log = True

    # Legacy suport for 'verbose' kwarg
    if should_log:
        should_log = kwargs.pop('verbose', True)

    # Legacy support for 'decorator' kwarg
    decorator = kwargs.pop('decorator', None)
    if isinstance(decorator, str):
        decorator = decorator.lower()
        if decorator == "info":
            level = logging.INFO
        elif decorator in ("warn", "warning"):
            level = logging.WARNING
        elif decorator == "error":
            level = logging.ERROR
    
    # Skip logging only for DEBUG and INFO levels if log=False
    # WARNING, ERROR, CRITICAL always log regardless of flag
    if not should_log and level <= logging.INFO:
        return
    
    # Use the original _log method stored on the class
    original_log = logging.Logger._original_log
    
    # Use lock for atomic output when using separators
    if sep or bottom:
        with _log_lock:
            # Top separator
            if sep:
                sep_line = SEP_CHAR * n_dashes
                original_log(
                    self, level, sep_line, (), exc_info, extra, 
                    stack_info, stacklevel)
            
            # Main message
            original_log(
                self, level, msg, args, exc_info, extra, stack_info, 
                stacklevel)
            
            # Bottom separator (shorter)
            if bottom:
                bottom_sep = SEP_CHAR * max(1, n_dashes // 5)
                original_log(
                    self, level, bottom_sep, (), 
                    exc_info, extra, stack_info, stacklevel)
    else:
        # No separators, just log normally without lock
        original_log(
            self, level, msg, args, exc_info, extra, stack_info, 
            stacklevel)


# Monkey-patch the Logger class to support sep/bottom/log kwargs
if not hasattr(logging.Logger, '_original_log'):
    logging.Logger._original_log = logging.Logger._log
    logging.Logger._log = _section_log


def setup_logging(
    experiment_name,
    log_dir="logs",
    log_file=None,
    level="info",
    log_to_file=True,
    log_to_console=False,
    verbose=False,
):
    # If we are logging to file, we try to resolve the log file first
    if log_to_file:
        if log_file is not None:
            if not os.path.isabs(log_file):
                print("Log file path must be absolute if provided directly."
                      f"Recieved: {log_file}")
                return None
            
            log_file = Path(log_file)
            log_dir = log_file.parent

            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Failed to create log directory: {log_dir}\n{e}")
                return None
        else:
            # If log directory is not a full path, 
            # place logs in <base_folder>/files/logs/<experiment_name>
            if not os.path.isabs(log_dir):
                # This file is in <base_folder>/util/core/setup_logging.py
                base_folder = Path(__file__).parent.parent.parent
                log_dir = base_folder / "files" / "logs" / experiment_name
                log_dir.mkdir(parents=True, exist_ok=True)

            # Only add experiment_name if not already in folder name
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            if experiment_name in log_dir.name:
                log_file = log_dir / f"{timestamp}.log"
                prune_pattern = "*.log"  # Prune all logs in this directory
            else:
                log_file = log_dir / f"{experiment_name}_{timestamp}.log"
                prune_pattern = f"{experiment_name}_*.log"

            _prune_old_logs(log_dir, prune_pattern)

    # Create formatters - we use short for both now
    file_formatter = ShortFormatter()
    console_formatter = ShortFormatter()

    root_logger = logging.getLogger()

    if isinstance(level, str):
        level = level.lower()
        level = log_dict.get(level, logging.INFO)

    root_logger.setLevel(level)

    # Check what handlers already exist to avoid duplicates
    has_file_handler = any(
        isinstance(h, logging.FileHandler) 
        for h in root_logger.handlers)
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and not 
        isinstance(h, logging.FileHandler) 
        for h in root_logger.handlers)

    # File handler (single experiment file)
    if log_to_file and not has_file_handler:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        if verbose:
            logging.getLogger(__name__).info(
                "Logs for experiment: %s", experiment_name)
            print(f"{'-'*50}\nLog file: {log_file}")

    # Console handler
    if log_to_console and not has_console_handler:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    return log_file


def _prune_old_logs(log_dir: Path, pattern: str):
    logs = sorted(
        log_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for old_log in logs[MAX_EXPERIMENT_LOGS:]:
        try:
            old_log.unlink()
        except Exception:
            pass