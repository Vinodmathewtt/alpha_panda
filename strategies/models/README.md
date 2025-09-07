# ML Models Directory

This directory contains trained ML models for use in trading strategies.

## Model Files
- `sample_momentum_v1.joblib`: Sample momentum prediction model for testing and development
- `.gitkeep`: Ensures directory structure is preserved in git

## Usage
Models are loaded automatically by ML strategy processors using the ModelLoader utility.

## Adding New Models
1. Train your model using scikit-learn or compatible framework
2. Save using joblib: `joblib.dump(model, 'model_name.joblib')`
3. Place in this directory
4. Reference by filename in strategy configuration