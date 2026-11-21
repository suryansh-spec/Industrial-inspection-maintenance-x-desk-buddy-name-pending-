#!/usr/bin/env python3
"""
Complete training pipeline for Signal Fault Classification.
Generates trained model, visualizations, and comprehensive reports.
"""

import os
import sys
import argparse
import numpy as np

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main


def setup_directories():
    """Create necessary directories."""
    dirs = ["models", "reports", "data"]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    print(f"✅ Directories created: {', '.join(dirs)}")


def check_data(data_dir: str, data_list: list) -> bool:
    """Check if data files exist."""
    missing = []
    for f in data_list:
        if not os.path.exists(os.path.join(data_dir, f)):
            missing.append(f)
    
    if missing:
        print(f"⚠️  Missing data files: {missing}")
        print(f"   Please download CWRU dataset and place in {data_dir}/")
        print(f"   Download from: https://engineering.case.edu/bearingdatacenter/download-data-file")
        return False
    return True


def run_training(args):
    """Run the training pipeline."""
    print("\n" + "=" * 70)
    print("SIGNAL FAULT CLASSIFICATION - TRAINING PIPELINE")
    print("=" * 70)
    
    # Setup
    setup_directories()
    
    # Check data
    if not check_data(args.data_dir, args.data_list):
        print("\n❌ Training aborted: missing data files")
        return False
    
    # Run main training
    try:
        # Override sys.argv for main()
        sys.argv = [
            "main.py",
            "--data_dir", args.data_dir,
            "--data_list"] + args.data_list + [
            "--data_info"] + args.data_info + [
            "--condition_list"] + args.condition_list + [
            "--window_size", str(args.window_size),
            "--num_data", str(args.num_data),
            "--epochs", str(args.epochs),
            "--lr", str(args.lr),
            "--lamda", str(args.lamda),
            "--early_stop", str(args.early_stop),
            "--train_size", str(args.train_size),
            "--batch_size", str(args.batch_size),
            "--model_path", args.model_path,
            "--detailed_eval"
        ]
        
        main()
        return True
        
    except Exception as e:
        print(f"\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Signal Fault Classification Training Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic training
  python train_pipeline.py
  
  # Custom parameters
  python train_pipeline.py --epochs 100 --lr 1e-3 --batch_size 128
  
  # Resume from checkpoint
  python train_pipeline.py --model_path models/cnn_model.pth --eval_only
        """
    )
    
    # Data arguments
    parser.add_argument('--data_dir', type=str, default='./data',
                        help='Directory containing CWRU .mat files')
    parser.add_argument('--data_list', nargs='+', default=['97.mat', '105.mat', '118.mat', '130.mat'],
                        help='List of .mat filenames')
    parser.add_argument('--data_info', nargs='+', default=['X097_DE_time', 'X105_DE_time', 'X118_DE_time', 'X130_DE_time'],
                        help='Variable names in .mat files')
    parser.add_argument('--condition_list', nargs='+', default=['Normal', 'IR', 'B', 'OR'],
                        help='Class labels')
    parser.add_argument('--window_size', type=int, default=1200,
                        help='Sliding window size')
    parser.add_argument('--num_data', type=int, default=4000,
                        help='Samples per class')
    
    # Training arguments
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--lamda', type=float, default=0.97)
    parser.add_argument('--early_stop', type=int, default=20)
    parser.add_argument('--train_size', type=float, default=0.8)
    parser.add_argument('--batch_size', type=int, default=64)
    
    # Model arguments
    parser.add_argument('--model_path', type=str, default='models/cnn_model.pth',
                        help='Path to save/load model')
    parser.add_argument('--eval_only', action='store_true',
                        help='Only evaluate existing model')
    parser.add_argument('--detailed_eval', action='store_true',
                        help='Run detailed evaluation')
    
    args = parser.parse_args()
    
    success = run_training(args)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()