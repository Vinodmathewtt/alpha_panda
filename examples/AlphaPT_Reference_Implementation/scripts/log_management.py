#!/usr/bin/env python3
"""Log management utility script for AlphaPT."""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from core.config.settings import Settings
from core.logging.log_management import (
    LogRotationManager,
    LogAnalyzer,
    LogExporter,
    ensure_log_directory_structure
)
from core.logging.log_channels import LogChannel, get_all_channels
from core.logging import get_channel_statistics


def print_colored(text: str, color: str = "white") -> None:
    """Print colored text."""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "bold": "\033[1m",
        "end": "\033[0m"
    }
    print(f"{colors.get(color, '')}{text}{colors['end']}")


def command_status(args) -> None:
    """Show status of all log channels."""
    print_colored("📊 AlphaPT Log Channel Status", "bold")
    print_colored("=" * 50, "cyan")
    
    settings = Settings()
    ensure_log_directory_structure(settings)
    
    rotation_manager = LogRotationManager(settings)
    status = rotation_manager.get_all_log_status()
    
    # Get channel statistics if multi-channel is available
    try:
        channel_stats = get_channel_statistics()
        multi_channel_available = True
    except Exception:
        multi_channel_available = False
        channel_stats = {}
    
    print(f"📁 Logs directory: {settings.logs_dir}")
    print(f"🔧 Multi-channel logging: {'✅ Available' if multi_channel_available else '❌ Not available'}")
    print()
    
    total_size_mb = 0
    healthy_channels = 0
    
    for channel_name, info in status.items():
        if info['exists']:
            size_mb = info['size_mb']
            total_size_mb += info.get('total_size_mb', size_mb)
            
            # Color code based on size
            if size_mb > 500:
                size_color = "red"
            elif size_mb > 100:
                size_color = "yellow"
            else:
                size_color = "green"
                healthy_channels += 1
            
            backup_count = len(info.get('backup_files', []))
            last_modified = info.get('modified')
            
            print_colored(f"📋 {channel_name.upper()}", "bold")
            print(f"   Size: ", end="")
            print_colored(f"{size_mb:.2f} MB", size_color)
            print(f"   Total (with backups): {info.get('total_size_mb', size_mb):.2f} MB")
            print(f"   Backup files: {backup_count}")
            if last_modified:
                print(f"   Last modified: {last_modified.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print()
        else:
            print_colored(f"📋 {channel_name.upper()}", "bold")
            print_colored("   Status: File not found", "yellow")
            print()
    
    print_colored("Summary", "bold")
    print(f"Total log size: {total_size_mb:.2f} MB")
    print(f"Healthy channels: {healthy_channels}/{len(status)}")


def command_analyze(args) -> None:
    """Analyze logs for a specific channel."""
    print_colored(f"🔍 Analyzing {args.channel} logs", "bold")
    print_colored("=" * 50, "cyan")
    
    settings = Settings()
    analyzer = LogAnalyzer(settings)
    
    try:
        channel = LogChannel(args.channel)
        analysis = analyzer.analyze_channel_logs(channel, args.lines)
        
        if 'error' in analysis:
            print_colored(f"❌ Error: {analysis['error']}", "red")
            return
        
        print(f"📊 Analysis of last {args.lines} lines:")
        print(f"   Total lines analyzed: {analysis['total_lines']}")
        print(f"   Error count: {analysis['error_count']}")
        print(f"   Warning count: {analysis['warning_count']}")
        print()
        
        if analysis['log_levels']:
            print_colored("Log Levels:", "bold")
            for level, count in analysis['log_levels'].items():
                color = "red" if level == "ERROR" else "yellow" if level == "WARNING" else "white"
                print_colored(f"   {level}: {count}", color)
            print()
        
        if analysis['components']:
            print_colored("Top Components:", "bold")
            sorted_components = sorted(analysis['components'].items(), key=lambda x: x[1], reverse=True)
            for component, count in sorted_components[:10]:
                print(f"   {component}: {count}")
            print()
        
        if analysis['recent_errors']:
            print_colored("Recent Errors:", "bold")
            for error in analysis['recent_errors'][-5:]:  # Show last 5 errors
                print_colored(f"   [{error['timestamp']}] {error['component']}", "red")
                print(f"     {error['message']}")
            print()
        
        if analysis['time_range']:
            print_colored("Time Range:", "bold")
            print(f"   From: {analysis['time_range'].get('start', 'N/A')}")
            print(f"   To: {analysis['time_range'].get('end', 'N/A')}")
    
    except ValueError:
        print_colored(f"❌ Error: Invalid channel '{args.channel}'", "red")
        print("Available channels:", ", ".join([c.value for c in LogChannel]))


def command_cleanup(args) -> None:
    """Clean up old log files."""
    print_colored(f"🧹 Cleaning up logs older than {args.days} days", "bold")
    print_colored("=" * 50, "cyan")
    
    settings = Settings()
    rotation_manager = LogRotationManager(settings)
    
    if args.dry_run:
        print_colored("🔍 DRY RUN - No files will be deleted", "yellow")
    
    cleanup_stats = rotation_manager.cleanup_old_logs(args.days)
    
    total_removed = 0
    for channel, count in cleanup_stats.items():
        if count > 0:
            color = "green" if count > 0 else "white"
            print_colored(f"   {channel}: {count} files removed", color)
            total_removed += count
        else:
            print(f"   {channel}: no files to remove")
    
    print()
    print_colored(f"Total files removed: {total_removed}", "green" if total_removed > 0 else "white")


def command_compress(args) -> None:
    """Compress old log files."""
    print_colored(f"📦 Compressing logs older than {args.days} days", "bold")
    print_colored("=" * 50, "cyan")
    
    settings = Settings()
    rotation_manager = LogRotationManager(settings)
    
    compression_stats = rotation_manager.compress_old_logs(args.days)
    
    total_compressed = 0
    for channel, count in compression_stats.items():
        if count > 0:
            print_colored(f"   {channel}: {count} files compressed", "green")
            total_compressed += count
        else:
            print(f"   {channel}: no files to compress")
    
    print()
    print_colored(f"Total files compressed: {total_compressed}", "green" if total_compressed > 0 else "white")


async def command_export(args) -> None:
    """Export logs in various formats."""
    print_colored(f"📤 Exporting {args.channel} logs to {args.format}", "bold")
    print_colored("=" * 50, "cyan")
    
    settings = Settings()
    exporter = LogExporter(settings)
    
    try:
        channel = LogChannel(args.channel)
        
        # Parse time range if provided
        time_range = None
        if args.start_date and args.end_date:
            start_date = datetime.fromisoformat(args.start_date)
            end_date = datetime.fromisoformat(args.end_date)
            time_range = (start_date, end_date)
        
        output_file = None
        if args.output:
            output_file = Path(args.output)
        
        exported_file = await exporter.export_channel_logs(
            channel, args.format, time_range, output_file
        )
        
        print_colored(f"✅ Exported to: {exported_file}", "green")
        
        # Show file size
        file_size = Path(exported_file).stat().st_size / 1024 / 1024
        print(f"File size: {file_size:.2f} MB")
    
    except ValueError:
        print_colored(f"❌ Error: Invalid channel '{args.channel}'", "red")
        print("Available channels:", ", ".join([c.value for c in LogChannel]))
    except Exception as e:
        print_colored(f"❌ Export failed: {e}", "red")


def command_health(args) -> None:
    """Show log health summary."""
    print_colored("🏥 Log Health Summary", "bold")
    print_colored("=" * 50, "cyan")
    
    settings = Settings()
    analyzer = LogAnalyzer(settings)
    
    summary = analyzer.get_log_health_summary()
    
    print(f"📊 Total channels: {summary['total_channels']}")
    print_colored(f"✅ Healthy: {summary['healthy_channels']}", "green")
    print_colored(f"⚠️  Warning: {summary['warning_channels']}", "yellow")
    print_colored(f"❌ Error: {summary['error_channels']}", "red")
    print()
    
    for channel, details in summary['channel_details'].items():
        status_color = {
            'healthy': 'green',
            'warning': 'yellow',
            'error': 'red'
        }.get(details['health_status'], 'white')
        
        print_colored(f"📋 {channel.upper()}", "bold")
        print_colored(f"   Status: {details['health_status']}", status_color)
        print(f"   Errors: {details['error_count']}")
        print(f"   Warnings: {details['warning_count']}")
        print(f"   Total lines: {details['total_lines']}")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AlphaPT Log Management Utility")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show log channel status")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze logs for a channel")
    analyze_parser.add_argument("channel", choices=[c.value for c in LogChannel], help="Log channel to analyze")
    analyze_parser.add_argument("--lines", type=int, default=1000, help="Number of lines to analyze (default: 1000)")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old log files")
    cleanup_parser.add_argument("--days", type=int, default=30, help="Remove files older than N days (default: 30)")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    
    # Compress command
    compress_parser = subparsers.add_parser("compress", help="Compress old log files")
    compress_parser.add_argument("--days", type=int, default=7, help="Compress files older than N days (default: 7)")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export logs in various formats")
    export_parser.add_argument("channel", choices=[c.value for c in LogChannel], help="Log channel to export")
    export_parser.add_argument("--format", choices=["json", "csv"], default="json", help="Export format (default: json)")
    export_parser.add_argument("--output", help="Output file path")
    export_parser.add_argument("--start-date", help="Start date (ISO format: 2024-01-01T00:00:00)")
    export_parser.add_argument("--end-date", help="End date (ISO format: 2024-01-01T23:59:59)")
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Show log health summary")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == "status":
            command_status(args)
        elif args.command == "analyze":
            command_analyze(args)
        elif args.command == "cleanup":
            command_cleanup(args)
        elif args.command == "compress":
            command_compress(args)
        elif args.command == "export":
            asyncio.run(command_export(args))
        elif args.command == "health":
            command_health(args)
    except KeyboardInterrupt:
        print_colored("\n⚠️ Operation cancelled by user", "yellow")
    except Exception as e:
        print_colored(f"❌ Error: {e}", "red")
        sys.exit(1)


if __name__ == "__main__":
    main()