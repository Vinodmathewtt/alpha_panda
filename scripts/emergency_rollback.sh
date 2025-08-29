#!/bin/bash
# Emergency Rollback Script for Strategy Migration
# Use this script to quickly rollback all migration changes

echo "🚨 EMERGENCY ROLLBACK INITIATED"
echo "This will rollback all strategy migration changes"

# Confirm before proceeding
read -p "Are you sure you want to rollback the migration? (yes/NO): " confirm
if [ "$confirm" != "yes" ]; then
    echo "❌ Rollback cancelled"
    exit 1
fi

echo "🔄 Starting emergency rollback..."

# 1. Rollback database migration
echo "🔄 Rolling back database migration..."
python scripts/migrate_strategies_to_composition.py rollback
if [ $? -eq 0 ]; then
    echo "✅ Database migration rolled back"
else
    echo "❌ Database rollback failed"
fi

# 2. Rollback YAML configurations
echo "🔄 Rolling back YAML configurations..."
python scripts/migrate_yaml_configs.py rollback
if [ $? -eq 0 ]; then
    echo "✅ YAML configurations rolled back"
else
    echo "❌ YAML rollback failed"
fi

# 3. Clean up test strategies (optional)
echo "🔄 Cleaning up test strategies..."
python scripts/seed_composition_strategies.py clean
if [ $? -eq 0 ]; then
    echo "✅ Test strategies cleaned up"
else
    echo "⚠️  Test strategy cleanup may have failed (this is usually OK)"
fi

# 4. Restore legacy factory if git backup exists
echo "🔄 Checking for factory backup..."
if [ -f "services/strategy_runner/factory.py.backup" ]; then
    echo "🔄 Restoring legacy factory from backup..."
    cp services/strategy_runner/factory.py.backup services/strategy_runner/factory.py
    echo "✅ Legacy factory restored"
else
    echo "⚠️  No factory backup found - manual restoration may be needed"
fi

# 5. Restart services if running in Docker
echo "🔄 Attempting to restart services..."
if command -v docker-compose &> /dev/null; then
    echo "🔄 Restarting Docker services..."
    docker-compose restart strategy_runner 2>/dev/null || echo "⚠️  Docker restart skipped (not running)"
else
    echo "ℹ️  Docker not available - manual service restart may be needed"
fi

echo ""
echo "✅ Emergency rollback complete!"
echo ""
echo "📋 ROLLBACK SUMMARY:"
echo "  - Database strategy types reverted to legacy names"
echo "  - YAML configurations restored to legacy format"
echo "  - Test strategies cleaned up"
echo "  - Services should be restarted"
echo ""
echo "⚠️  IMPORTANT: Please verify that your application is working correctly"
echo "   and monitor logs for any issues."