#!/usr/bin/env python3
"""
Script to create initial migration for Alpha Panda schema fixes.
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Create initial migration for all schema fixes."""
    try:
        print("Creating initial migration for Alpha Panda schema fixes...")
        
        # Ensure we're in the project root
        project_root = Path(__file__).parent.parent
        subprocess.run([
            "alembic", "-c", str(project_root / "alembic.ini"), 
            "revision", "--autogenerate", 
            "-m", "Add unique constraints and JSONB optimizations"
        ], cwd=project_root, check=True)
        
        print("✅ Migration created successfully!")
        print("To apply the migration, run: alembic upgrade head")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create migration: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()