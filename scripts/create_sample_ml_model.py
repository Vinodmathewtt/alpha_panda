"""
Create sample ML model for testing ML strategies
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib
import os
from pathlib import Path


def create_sample_momentum_model():
    """Create a sample ML model for testing"""
    
    # Generate sample training data
    np.random.seed(42)
    n_samples = 1000
    
    # Features: [total_return, short_momentum, volatility, price, history_length]
    features = np.random.randn(n_samples, 5)
    
    # Labels: 1 = BUY, 0 = SELL (based on simple momentum rule)
    labels = (features[:, 1] > 0.1).astype(int)  # Buy if short momentum > 0.1
    
    # Train model
    X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, random_state=42)
    
    model = RandomForestClassifier(n_estimators=10, random_state=42, max_depth=5)
    model.fit(X_train, y_train)
    
    # Save model
    script_dir = Path(__file__).parent
    model_dir = script_dir.parent / "strategies" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "sample_momentum_v1.joblib"
    
    joblib.dump(model, str(model_path))
    print(f"✅ Created sample model: {model_path}")
    print(f"📊 Accuracy: {model.score(X_test, y_test):.2f}")
    
    return str(model_path)


if __name__ == "__main__":
    create_sample_momentum_model()