import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import pickle
import os

# GROSEN: Generate synthetic geotechnical training data calibrated against Saito creep stages.
def generate_synthetic_geotech_data(num_samples=25000):
    print("Generating synthetic geotechnical sensor data...")
    np.random.seed(42)
    
    # Synthesize normal baseline regime samples with low creep velocity.
    n_norm = int(num_samples * 0.60)
    norm_tilt = np.random.normal(loc=2.0, scale=0.8, size=n_norm)
    norm_vel = np.random.uniform(0.1, 1.8, size=n_norm)
    norm_vrms = np.random.uniform(0.01, 0.05, size=n_norm)
    norm_vpk = np.random.uniform(0.08, 0.25, size=n_norm)
    norm_labels = np.zeros(n_norm, dtype=int)
    
    # Synthesize secondary accelerating creep transition regime samples.
    n_warn = int(num_samples * 0.20)
    warn_tilt = np.random.normal(loc=4.5, scale=1.5, size=n_warn)
    warn_vel = np.random.uniform(2.5, 8.5, size=n_warn)
    warn_vrms = np.random.uniform(0.05, 0.14, size=n_warn)
    warn_vpk = np.random.uniform(0.30, 0.75, size=n_warn)
    warn_labels = np.random.binomial(1, 0.50, size=n_warn)
    
    # Synthesize tertiary runaway creep and slope shear failure samples.
    n_fail = num_samples - n_norm - n_warn
    fail_tilt = np.random.normal(loc=12.0, scale=3.5, size=n_fail)
    fail_vel = np.random.uniform(9.0, 25.0, size=n_fail)
    fail_vrms = np.random.uniform(0.15, 0.50, size=n_fail)
    fail_vpk = np.random.uniform(0.80, 2.50, size=n_fail)
    fail_labels = np.ones(n_fail, dtype=int)
    
    df = pd.DataFrame({
        'tilt_total_deg': np.clip(np.concatenate([norm_tilt, warn_tilt, fail_tilt]), 0, 45),
        'displacement_velocity': np.clip(np.concatenate([norm_vel, warn_vel, fail_vel]), 0, 30),
        'vibration_rms_g': np.clip(np.concatenate([norm_vrms, warn_vrms, fail_vrms]), 0, 1.0),
        'vibration_peak_g': np.clip(np.concatenate([norm_vpk, warn_vpk, fail_vpk]), 0, 3.0),
        'label': np.concatenate([norm_labels, warn_labels, fail_labels])
    }).sample(frac=1, random_state=42).reset_index(drop=True)
    
    return df

# GROSEN: Train XGBoost classifier on geotechnical features and export serialized model artifact.
def train_and_export_model():
    # Generate balanced geotechnical dataset for model training.
    df = generate_synthetic_geotech_data()
    
    X = df[['tilt_total_deg', 'displacement_velocity', 'vibration_rms_g', 'vibration_peak_g']]
    y = df['label']
    
    # Partition geotechnical dataset into training and testing subsets.
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train gradient boosted decision tree classifier with calibrated hyperparameters.
    print("Training XGBoost AI Model with geotechnical progression calibration...")
    model = xgb.XGBClassifier(
        n_estimators=120, 
        learning_rate=0.08, 
        max_depth=4, 
        eval_metric='logloss',
        random_state=42
    )
    model.fit(X_train, y_train)
    
    # Calculate accuracy and print classification metrics on test data.
    predictions = model.predict(X_test)
    acc = accuracy_score(y_test, predictions)
    print(f"\nModel Training Complete! Accuracy: {acc * 100:.2f}%")
    print("\nClassification Report:")
    print(classification_report(y_test, predictions))
    
    # Serialize trained model artifact to pickle file for backend inference.
    model_filename = 'model.pkl'
    with open(model_filename, 'wb') as f:
        pickle.dump(model, f)
    print(f"\nSuccess: AI Model saved to {os.path.abspath(model_filename)}")

# Entry point to execute dataset synthesis and model training pipeline.
if __name__ == "__main__":
    train_and_export_model()