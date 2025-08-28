"""Log management utilities for AlphaPT multi-channel logging."""

import os
import gzip
import shutil
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

from core.logging.log_channels import LOG_CHANNELS, LogChannel, get_channel_config
from core.config.settings import Settings


class LogRotationManager:
    """Manages log rotation and archival for all channels."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logs_dir = settings.logs_dir
        
    def get_log_file_info(self, channel: LogChannel) -> Dict[str, any]:
        """Get information about a log file."""
        config = get_channel_config(channel)
        log_file = config.get_file_path(self.logs_dir)
        
        if not log_file.exists():
            return {
                'exists': False,
                'size_bytes': 0,
                'size_mb': 0,
                'modified': None,
                'backup_files': []
            }
        
        stat = log_file.stat()
        backup_files = self._get_backup_files(log_file)
        
        return {
            'exists': True,
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / 1024 / 1024, 2),
            'modified': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            'backup_files': backup_files,
            'total_size_mb': self._calculate_total_size(log_file, backup_files)
        }
    
    def _get_backup_files(self, log_file: Path) -> List[Dict[str, any]]:
        """Get list of backup files for a log file."""
        backup_files = []
        
        # Look for numbered backup files (.1, .2, etc.)
        for i in range(1, 100):  # Check up to 100 backup files
            backup_path = Path(f"{log_file}.{i}")
            if backup_path.exists():
                stat = backup_path.stat()
                backup_files.append({
                    'path': str(backup_path),
                    'size_bytes': stat.st_size,
                    'size_mb': round(stat.st_size / 1024 / 1024, 2),
                    'modified': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                })
            else:
                break
        
        return backup_files
    
    def _calculate_total_size(self, log_file: Path, backup_files: List[Dict]) -> float:
        """Calculate total size including backups."""
        total_bytes = 0
        if log_file.exists():
            total_bytes += log_file.stat().st_size
        
        for backup in backup_files:
            total_bytes += backup['size_bytes']
        
        return round(total_bytes / 1024 / 1024, 2)
    
    def get_all_log_status(self) -> Dict[str, Dict]:
        """Get status of all log files."""
        status = {}
        
        for channel in LogChannel:
            status[channel.value] = self.get_log_file_info(channel)
        
        return status
    
    def cleanup_old_logs(self, older_than_days: Optional[int] = None) -> Dict[str, int]:
        """Clean up old log files based on retention policies."""
        cleanup_stats = {}
        
        for channel in LogChannel:
            config = get_channel_config(channel)
            retention_days = older_than_days or config.retention_days
            
            files_removed = self._cleanup_channel_logs(channel, retention_days)
            cleanup_stats[channel.value] = files_removed
        
        return cleanup_stats
    
    def _cleanup_channel_logs(self, channel: LogChannel, retention_days: int) -> int:
        """Clean up logs for a specific channel."""
        config = get_channel_config(channel)
        log_file = config.get_file_path(self.logs_dir)
        
        if not log_file.exists():
            return 0
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        files_removed = 0
        
        # Remove old backup files
        backup_files = self._get_backup_files(log_file)
        for backup in backup_files:
            if backup['modified'] < cutoff_date:
                try:
                    os.remove(backup['path'])
                    files_removed += 1
                except OSError:
                    pass  # File might have been removed already
        
        return files_removed
    
    def compress_old_logs(self, older_than_days: int = 7) -> Dict[str, int]:
        """Compress old log files to save space."""
        compression_stats = {}
        
        for channel in LogChannel:
            files_compressed = self._compress_channel_logs(channel, older_than_days)
            compression_stats[channel.value] = files_compressed
        
        return compression_stats
    
    def _compress_channel_logs(self, channel: LogChannel, older_than_days: int) -> int:
        """Compress logs for a specific channel."""
        config = get_channel_config(channel)
        log_file = config.get_file_path(self.logs_dir)
        
        if not log_file.exists():
            return 0
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        files_compressed = 0
        
        backup_files = self._get_backup_files(log_file)
        for backup in backup_files:
            backup_path = Path(backup['path'])
            
            # Skip if already compressed
            if backup_path.suffix == '.gz':
                continue
            
            if backup['modified'] < cutoff_date:
                try:
                    self._compress_file(backup_path)
                    files_compressed += 1
                except Exception:
                    pass  # Continue with other files
        
        return files_compressed
    
    def _compress_file(self, file_path: Path) -> None:
        """Compress a single file using gzip."""
        compressed_path = Path(f"{file_path}.gz")
        
        with open(file_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove original file after successful compression
        os.remove(file_path)


class LogAnalyzer:
    """Analyze log files for insights and statistics."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logs_dir = settings.logs_dir
    
    def analyze_channel_logs(self, channel: LogChannel, last_n_lines: int = 1000) -> Dict[str, any]:
        """Analyze logs for a specific channel."""
        config = get_channel_config(channel)
        log_file = config.get_file_path(self.logs_dir)
        
        if not log_file.exists():
            return {'error': 'Log file does not exist'}
        
        analysis = {
            'total_lines': 0,
            'log_levels': {},
            'components': {},
            'error_count': 0,
            'warning_count': 0,
            'time_range': {},
            'recent_errors': []
        }
        
        try:
            # Read last n lines of the file
            lines = self._tail_file(log_file, last_n_lines)
            
            for line in lines:
                analysis['total_lines'] += 1
                
                try:
                    # Try to parse as JSON
                    log_entry = json.loads(line.strip())
                    
                    # Analyze log level
                    level = log_entry.get('level', 'unknown')
                    analysis['log_levels'][level] = analysis['log_levels'].get(level, 0) + 1
                    
                    # Count errors and warnings
                    if level == 'ERROR':
                        analysis['error_count'] += 1
                        analysis['recent_errors'].append({
                            'timestamp': log_entry.get('timestamp'),
                            'message': log_entry.get('message', '')[:200],
                            'component': log_entry.get('component', 'unknown')
                        })
                    elif level == 'WARNING':
                        analysis['warning_count'] += 1
                    
                    # Analyze components
                    component = log_entry.get('component', 'unknown')
                    analysis['components'][component] = analysis['components'].get(component, 0) + 1
                    
                    # Track time range
                    timestamp = log_entry.get('timestamp')
                    if timestamp:
                        if not analysis['time_range']:
                            analysis['time_range']['start'] = timestamp
                        analysis['time_range']['end'] = timestamp
                
                except json.JSONDecodeError:
                    # Non-JSON line, just count it
                    pass
        
        except Exception as e:
            analysis['error'] = f"Failed to analyze log file: {e}"
        
        # Limit recent errors to last 10
        analysis['recent_errors'] = analysis['recent_errors'][-10:]
        
        return analysis
    
    def _tail_file(self, file_path: Path, n_lines: int) -> List[str]:
        """Read last n lines from a file efficiently."""
        try:
            with open(file_path, 'rb') as f:
                # Go to end of file
                f.seek(0, 2)
                file_size = f.tell()
                
                # Read chunks from end until we have enough lines
                lines = []
                buffer_size = min(8192, file_size)
                position = file_size
                
                while len(lines) < n_lines and position > 0:
                    # Read a chunk from the current position
                    chunk_start = max(0, position - buffer_size)
                    f.seek(chunk_start)
                    chunk = f.read(position - chunk_start).decode('utf-8', errors='ignore')
                    
                    # Split into lines and prepend to our list
                    chunk_lines = chunk.split('\n')
                    lines = chunk_lines + lines
                    
                    position = chunk_start
                
                # Return the last n_lines, excluding empty lines
                return [line for line in lines[-n_lines:] if line.strip()]
        
        except Exception:
            return []
    
    def get_log_health_summary(self) -> Dict[str, any]:
        """Get a health summary of all log channels."""
        summary = {
            'total_channels': len(LogChannel),
            'healthy_channels': 0,
            'warning_channels': 0,
            'error_channels': 0,
            'channel_details': {}
        }
        
        for channel in LogChannel:
            analysis = self.analyze_channel_logs(channel, last_n_lines=100)
            
            # Determine channel health
            health_status = 'healthy'
            if analysis.get('error_count', 0) > 10:
                health_status = 'error'
                summary['error_channels'] += 1
            elif analysis.get('warning_count', 0) > 5:
                health_status = 'warning'
                summary['warning_channels'] += 1
            else:
                summary['healthy_channels'] += 1
            
            summary['channel_details'][channel.value] = {
                'health_status': health_status,
                'error_count': analysis.get('error_count', 0),
                'warning_count': analysis.get('warning_count', 0),
                'total_lines': analysis.get('total_lines', 0)
            }
        
        return summary


class LogExporter:
    """Export logs in various formats for analysis."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logs_dir = settings.logs_dir
    
    async def export_channel_logs(
        self, 
        channel: LogChannel, 
        output_format: str = 'json',
        time_range: Optional[Tuple[datetime, datetime]] = None,
        output_file: Optional[Path] = None
    ) -> str:
        """Export logs for a channel in specified format."""
        
        config = get_channel_config(channel)
        log_file = config.get_file_path(self.logs_dir)
        
        if not log_file.exists():
            raise FileNotFoundError(f"Log file for channel {channel.value} not found")
        
        # Generate output filename if not provided
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.logs_dir / f"{channel.value}_export_{timestamp}.{output_format}"
        
        if output_format == 'json':
            await self._export_json(log_file, output_file, time_range)
        elif output_format == 'csv':
            await self._export_csv(log_file, output_file, time_range)
        else:
            raise ValueError(f"Unsupported export format: {output_format}")
        
        return str(output_file)
    
    async def _export_json(self, input_file: Path, output_file: Path, time_range: Optional[Tuple[datetime, datetime]]):
        """Export logs in JSON format."""
        with open(input_file, 'r') as f_in, open(output_file, 'w') as f_out:
            f_out.write('[\n')
            first = True
            
            for line in f_in:
                try:
                    log_entry = json.loads(line.strip())
                    
                    # Filter by time range if specified
                    if time_range:
                        timestamp_str = log_entry.get('timestamp')
                        if timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            if not (time_range[0] <= timestamp <= time_range[1]):
                                continue
                    
                    if not first:
                        f_out.write(',\n')
                    json.dump(log_entry, f_out, indent=2)
                    first = False
                
                except json.JSONDecodeError:
                    continue
            
            f_out.write('\n]')
    
    async def _export_csv(self, input_file: Path, output_file: Path, time_range: Optional[Tuple[datetime, datetime]]):
        """Export logs in CSV format."""
        import csv
        
        fieldnames = ['timestamp', 'level', 'component', 'message', 'correlation_id']
        
        with open(input_file, 'r') as f_in, open(output_file, 'w', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            
            for line in f_in:
                try:
                    log_entry = json.loads(line.strip())
                    
                    # Filter by time range if specified
                    if time_range:
                        timestamp_str = log_entry.get('timestamp')
                        if timestamp_str:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            if not (time_range[0] <= timestamp <= time_range[1]):
                                continue
                    
                    # Extract CSV fields
                    row = {
                        'timestamp': log_entry.get('timestamp', ''),
                        'level': log_entry.get('level', ''),
                        'component': log_entry.get('component', ''),
                        'message': log_entry.get('message', ''),
                        'correlation_id': log_entry.get('correlation_id', '')
                    }
                    
                    writer.writerow(row)
                
                except json.JSONDecodeError:
                    continue


# Utility functions
def ensure_log_directory_structure(settings: Settings) -> None:
    """Ensure the complete log directory structure exists."""
    from core.logging.log_channels import create_log_directory_structure
    create_log_directory_structure(settings.logs_dir)


def get_log_rotation_manager(settings: Settings) -> LogRotationManager:
    """Get a log rotation manager instance."""
    return LogRotationManager(settings)


def get_log_analyzer(settings: Settings) -> LogAnalyzer:
    """Get a log analyzer instance."""
    return LogAnalyzer(settings)


def get_log_exporter(settings: Settings) -> LogExporter:
    """Get a log exporter instance."""
    return LogExporter(settings)