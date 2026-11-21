#!/usr/bin/env python3
"""
Main entry point for Signal Fault Classification Pipeline.
Trains CNN on CWRU bearing fault dataset with visualization.
"""

import argparse
import os
import sys
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arguments import get_args
from dataset import get_dataloaders
from train import train_model, load_model
from test import evaluate, evaluate_detailed
from preprocess import CWRUPreprocessor, VibrationPreprocessor


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Signal Fault Classification Pipeline')
    
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
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    print("=" * 60)
    print("SIGNAL FAULT CLASSIFICATION PIPELINE")
    print("=" * 60)
    print(f"Data directory: {args.data_dir}")
    print(f"Classes: {args.condition_list}")
    print(f"Window size: {args.window_size}")
    print(f"Samples per class: {args.num_data}")
    print(f"Epochs: {args.epochs}")
    print(f"Learning rate: {args.lr}")
    print(f"Batch size: {args.batch_size}")
    print(f"Early stopping: {args.early_stop}")
    print("=" * 60)
    
    # Initialize preprocessor
    preprocessor = CWRUPreprocessor(
        data_dir=args.data_dir,
        data_list=args.data_list,
        data_info=args.data_info,
        condition_list=args.condition_list,
        window_size=args.window_size,
        num_data=args.num_data
    )
    
    # Load and preprocess data
    print("\n📊 Loading and preprocessing data...")
    X, Y = preprocessor.get_data()
    
    # Visualize signal samples
    print("\n📈 Generating signal sample visualizations...")
    preprocessor.visualize_samples(X, Y, args.condition_list, 
                                   save_path="reports/signal_samples.png",
                                   n_samples=4)
    
    # Create data loaders
    print("\n🔄 Creating data loaders...")
    train_dl, valid_dl, test_dl = get_dataloaders(X, Y, args)
    
    if args.eval_only:
        # Evaluation only mode
        print(f"\n🔍 Loading model from {args.model_path}...")
        model, checkpoint = load_model(args.model_path)
        model.eval()
        
        if args.detailed_eval:
            results = evaluate_detailed(test_dl, model, args.condition_list)
        else:
            evaluate(test_dl, model, args.condition_list)
        return
    
    # Train model
    print("\n🚀 Starting training...")
    model, result_dict = train_model(args, train_dl, valid_dl, 
                                     class_names=args.condition_list)
    
    # Evaluate
    print("\n📊 Evaluating on test set...")
    evaluate(test_dl, model, args.condition_list)
    
    # Detailed evaluation
    if args.detailed_eval:
        evaluate_detailed(test_dl, model, args.condition_list)
    
    print("\n" + "=" * 60)
    print("✅ PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Best epoch: {result_dict.get('stop_point', 'N/A')}")
    print(f"Model saved to: {args.model_path}")
    print(f"Reports saved to: reports/")
    print("=" * 60)


if __name__ == '__main__':
    main()