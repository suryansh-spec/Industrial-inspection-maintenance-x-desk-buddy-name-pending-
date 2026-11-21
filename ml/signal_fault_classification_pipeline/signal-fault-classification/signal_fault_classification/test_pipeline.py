#!/usr/bin/env python3
"""
Test script to verify the ML pipeline works correctly.
Run this before training to verify all components work.
"""

import os
import sys
import numpy as np
import tempfile

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test all imports work."""
    print("Testing imports...")
    try:
        import torch
        import numpy as np
        import scipy
        import sklearn
        import matplotlib
        import tqdm
        print("✅ Core dependencies OK")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    
    try:
        from signal_fault_classification.model import CNNModel
        from signal_fault_classification.dataset import get_dataloaders, SignalDataset
        from signal_fault_classification.train import train_model, load_model
        from signal_fault_classification.test import evaluate, evaluate_detailed
        from signal_fault_classification.preprocess import CWRUPreprocessor, VibrationPreprocessor
        from signal_fault_classification.visualize import (
            plot_training_curves, plot_confusion_matrix, 
            plot_per_class_metrics, generate_training_report
        )
        print("✅ Pipeline modules OK")
    except ImportError as e:
        print(f"❌ Pipeline import failed: {e}")
        return False
    
    return True


def test_model():
    """Test model creation and forward pass."""
    print("\nTesting model...")
    try:
        import torch
        from signal_fault_classification.model import CNNModel
        
        model = CNNModel()
        print(f"✅ Model created: {sum(p.numel() for p in model.parameters()):,} parameters")
        
        # Test forward pass
        x = torch.randn(2, 1, 1200)
        out = model(x)
        assert out.shape == (2, 4), f"Expected (2, 4), got {out.shape}"
        print(f"✅ Forward pass OK: {out.shape}")
        
    except Exception as e:
        print(f"❌ Model test failed: {e}")
        return False
    
    return True


def test_dataset():
    """Test dataset and dataloaders."""
    print("\nTesting dataset...")
    try:
        import torch
        from signal_fault_classification.dataset import get_dataloaders, SignalDataset
        
        # Create dummy data
        X = np.random.randn(1000, 1200).astype(np.float32)
        Y = np.zeros((1000, 4), dtype=np.float32)
        for i in range(4):
            Y[i*250:(i+1)*250, i] = 1
        
        class Opt:
            train_size = 0.8
            batch_size = 64
        
        train_dl, valid_dl, test_dl = get_dataloaders(X, Y, Opt())
        
        print(f"✅ DataLoaders created: train={len(train_dl)}, valid={len(valid_dl)}, test={len(test_dl)}")
        
        # Test batch
        for x, y in train_dl:
            assert x.shape == (64, 1, 1200), f"Expected (64, 1, 1200), got {x.shape}"
            assert y.shape == (64,), f"Expected (64,), got {y.shape}"
            print(f"✅ Batch shapes OK: x={x.shape}, y={y.shape}")
            break
            
    except Exception as e:
        print(f"❌ Dataset test failed: {e}")
        return False
    
    return True


def test_preprocess():
    """Test preprocessor with dummy data."""
    print("\nTesting preprocessor...")
    try:
        from signal_fault_classification.preprocess import CWRUPreprocessor, VibrationPreprocessor
        import scipy.io as sio
        
        # Create temporary .mat files
        with tempfile.TemporaryDirectory() as tmpdir:
            for fname, varname, label in [
                ('97.mat', 'X097_DE_time', 'Normal'),
                ('105.mat', 'X105_DE_time', 'Inner Race'),
                ('118.mat', 'X118_DE_time', 'Ball'),
                ('130.mat', 'X130_DE_time', 'Outer Race')
            ]:
                # Generate synthetic signal
                t = np.arange(120000)
                signal = np.sin(2 * np.pi * 50 * t / 12000)
                signal += 0.5 * np.sin(2 * np.pi * 120 * t / 12000)
                signal += 0.1 * np.random.randn(len(t))
                sio.savemat(os.path.join(tmpdir, fname), {varname: signal.reshape(-1, 1)})
            
            preprocessor = CWRUPreprocessor(
                data_dir=tmpdir,
                data_list=['97.mat', '105.mat', '118.mat', '130.mat'],
                data_info=['X097_DE_time', 'X105_DE_time', 'X118_DE_time', 'X130_DE_time'],
                condition_list=['Normal', 'Inner Race', 'Ball', 'Outer Race'],
                window_size=1200,
                num_data=100
            )
            
            X, Y = preprocessor.get_data()
            assert X.shape == (400, 1200)
            assert Y.shape == (400, 4)
            print(f"✅ Preprocessor OK: X={X.shape}, Y={Y.shape}")
        
    except Exception as e:
        print(f"❌ Preprocess test failed: {e}")
        return False
    
    return True


def test_visualize():
    """Test visualization functions."""
    print("\nTesting visualizations...")
    try:
        from signal_fault_classification.visualize import (
            plot_training_curves, plot_confusion_matrix,
            plot_per_class_metrics, generate_training_report
        )
        
        # Dummy data
        result_dict = {
            'train_loss': [0.8, 0.6, 0.45, 0.35, 0.3, 0.28, 0.27, 0.26, 0.26, 0.27],
            'valid_loss': [0.75, 0.55, 0.4, 0.32, 0.28, 0.26, 0.26, 0.27, 0.28, 0.3],
            'stop_point': 7
        }
        
        y_true = np.random.randint(0, 4, 1000)
        y_pred = np.random.randint(0, 4, 1000)
        for i in range(len(y_pred)):
            if np.random.rand() < 0.8:
                y_pred[i] = y_true[i]
        
        os.makedirs("test_output", exist_ok=True)
        plot_training_curves(result_dict, "test_output/training_curves.png")
        plot_confusion_matrix(y_true, y_pred, save_path="test_output/confusion_matrix.png")
        plot_per_class_metrics(y_true, y_pred, save_path="test_output/per_class_metrics.png")
        
        print("✅ Visualizations generated in test_output/")
        
    except Exception as e:
        print(f"❌ Visualization test failed: {e}")
        return False
    
    return True


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("ML PIPELINE TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Model", test_model),
        ("Dataset", test_dataset),
        ("Preprocess", test_preprocess),
        ("Visualizations", test_visualize),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED")
    
    return all_passed


if __name__ == "__main__":
    import tempfile
    success = run_all_tests()
    sys.exit(0 if success else 1)