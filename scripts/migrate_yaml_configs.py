#!/usr/bin/env python3
"""
YAML Configuration Migration Script
Migrate YAML configuration files to composition architecture
"""
import yaml
from pathlib import Path
import sys


def migrate_yaml_configs():
    """Migrate YAML configuration files to composition architecture"""
    
    config_path = Path(__file__).parent.parent / "strategies" / "configs"
    
    if not config_path.exists():
        print(f"❌ Configuration directory not found: {config_path}")
        return
    
    migration_mapping = {
        "SimpleMomentumStrategy": "MomentumProcessor",
        "MomentumStrategy": "MomentumProcessor",
        "MeanReversionStrategy": "MeanReversionProcessor",
    }
    
    parameter_migrations = {
        "MomentumProcessor": {"lookback_period": "lookback_periods"},
        "MeanReversionProcessor": {
            "window_size": "lookback_periods",  # Mean reversion uses window_size
            "entry_threshold": "std_deviation_threshold"  # Map entry_threshold to std_deviation_threshold
        }
    }
    
    migrated_count = 0
    
    for config_file in config_path.glob("*.yaml"):
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Check if migration is needed
            old_class = config.get("strategy_class")
            if old_class in migration_mapping:
                new_class = migration_mapping[old_class]
                config["strategy_class"] = new_class
                
                # Migrate parameters
                if new_class in parameter_migrations:
                    params = config.get("parameters", {})
                    for old_param, new_param in parameter_migrations[new_class].items():
                        if old_param in params:
                            params[new_param] = params.pop(old_param)
                
                # Add composition flag
                config["use_composition"] = True
                
                # Write updated config
                with open(config_file, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False)
                
                print(f"✓ Migrated {config_file.name}: {old_class} -> {new_class}")
                migrated_count += 1
            else:
                print(f"? No migration needed for {config_file.name}: {old_class}")
                
        except Exception as e:
            print(f"❌ Failed to migrate {config_file}: {e}")
    
    print(f"✓ Configuration migration complete: {migrated_count} files migrated")


def rollback_yaml_configs():
    """Rollback YAML configuration migration"""
    
    config_path = Path(__file__).parent.parent / "strategies" / "configs"
    
    if not config_path.exists():
        print(f"❌ Configuration directory not found: {config_path}")
        return
    
    # Reverse migration mapping
    reverse_mapping = {
        "MomentumProcessor": "MomentumStrategy",  # Use generic name
        "MeanReversionProcessor": "MeanReversionStrategy",
    }
    
    reverse_parameter_migrations = {
        "MomentumProcessor": {"lookback_periods": "lookback_period"},
        "MeanReversionProcessor": {
            "lookback_periods": "lookback_period",
            "std_deviation_threshold": "std_dev_threshold"
        }
    }
    
    rolled_back_count = 0
    
    for config_file in config_path.glob("*.yaml"):
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Check if rollback is needed
            new_class = config.get("strategy_class")
            if new_class in reverse_mapping:
                old_class = reverse_mapping[new_class]
                config["strategy_class"] = old_class
                
                # Rollback parameters
                if new_class in reverse_parameter_migrations:
                    params = config.get("parameters", {})
                    for new_param, old_param in reverse_parameter_migrations[new_class].items():
                        if new_param in params:
                            params[old_param] = params.pop(new_param)
                
                # Remove composition flag
                if "use_composition" in config:
                    del config["use_composition"]
                
                # Write updated config
                with open(config_file, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False)
                
                print(f"✓ Rolled back {config_file.name}: {new_class} -> {old_class}")
                rolled_back_count += 1
            else:
                print(f"? No rollback needed for {config_file.name}: {new_class}")
                
        except Exception as e:
            print(f"❌ Failed to rollback {config_file}: {e}")
    
    print(f"✓ Configuration rollback complete: {rolled_back_count} files rolled back")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        print("🔄 Starting YAML configuration rollback...")
        rollback_yaml_configs()
    else:
        print("🚀 Starting YAML configuration migration...")
        migrate_yaml_configs()