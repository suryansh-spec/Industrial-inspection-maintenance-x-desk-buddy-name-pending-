import torch
import numpy as np
from tqdm import tqdm
from model import CNNModel
import torch.nn.functional as F
import pickle
import os
import json
from visualize import plot_training_curves, generate_training_report


def train_model(opt, train_dl, valid_dl, class_names=None, save_dir="models"):
    """
    Train the CNN model with early stopping and visualization.
    
    Args:
        opt: Training options
        train_dl: Training data loader
        valid_dl: Validation data loader
        class_names: List of class names for reporting
        save_dir: Directory to save model and reports
        
    Returns:
        best_model: Trained model
        result_dict: Training history
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CNNModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=opt.lr)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda e: opt.lamda ** e)
    criterion = torch.nn.CrossEntropyLoss()

    dict_result = {
        'train_loss': [], 
        'valid_loss': [], 
        'lr_history': [],
        'stop_point': 0
    }
    best_loss = float('inf')
    early_stop_count = 0
    best_model_state = None

    pbar = tqdm(range(opt.epochs), desc="Training")

    for epoch in pbar:
        model.train()
        train_loss = []
        for x, y in train_dl:
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            train_loss.append(loss.item())
        scheduler.step()
        
        # Track learning rate
        current_lr = optimizer.param_groups[0]['lr']
        dict_result['lr_history'].append(current_lr)
        
        pbar.set_postfix({'train_loss': np.mean(train_loss), 'lr': current_lr})

        # Validation
        model.eval()
        val_loss = []
        with torch.no_grad():
            for x, y in valid_dl:
                val_loss.append(criterion(model(x), y).item())

        train_avg = np.mean(train_loss)
        valid_avg = np.mean(val_loss)
        dict_result['train_loss'].append(train_avg)
        dict_result['valid_loss'].append(valid_avg)

        if valid_avg < best_loss:
            best_loss = valid_avg
            early_stop_count = 0
            dict_result['stop_point'] = epoch + 1
            best_model_state = model.state_dict().copy()
            
        else:
            early_stop_count += 1
            if early_stop_count > opt.early_stop:
                print(f"\nEarly stopping at epoch {epoch + 1}")
                break

    # Load best model
    model.load_state_dict(best_model_state)
    
    # Save model
    os.makedirs(save_dir, exist_ok=True)
    model_path = os.path.join(save_dir, "cnn_model.pth")
    torch.save({
        'model_state_dict': best_model_state,
        'model_config': {
            'input_channels': 1,
            'num_classes': 4,
            'window_size': 1200
        },
        'training_history': dict_result,
        'optimizer_state_dict': optimizer.state_dict(),
    }, model_path)
    print(f"✅ Model saved to {model_path}")
    
    # Save training history
    history_path = os.path.join(save_dir, "training_history.json")
    with open(history_path, 'w') as f:
        # Convert numpy types to native Python types
        serializable = {k: [float(v) if isinstance(v, (np.floating, np.integer)) else v 
                           for v in vals] if isinstance(vals, list) else vals 
                       for k, vals in dict_result.items()}
        json.dump(serializable, f, indent=2)
    print(f"✅ Training history saved to {history_path}")
    
    # Generate training curves
    os.makedirs("reports", exist_ok=True)
    plot_training_curves(dict_result, "reports/training_curves.png")
    
    return model, dict_result


def load_model(model_path: str, device: str = None):
    """
    Load a trained model from checkpoint.
    
    Args:
        model_path: Path to the .pth file
        device: Device to load model on ('cuda' or 'cpu')
        
    Returns:
        model: Loaded CNNModel
        checkpoint: Full checkpoint dict
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    checkpoint = torch.load(model_path, map_location=device)
    model = CNNModel().to(device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    print(f"✅ Model loaded from {model_path}")
    print(f"   Classes: {checkpoint['model_config']['num_classes']}")
    print(f"   Window size: {checkpoint['model_config']['window_size']}")
    print(f"   Best epoch: {checkpoint['training_history'].get('stop_point', 'N/A')}")
    
    return model, checkpoint


if __name__ == "__main__":
    # Quick test
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test_load', type=str, help='Test loading a model')
    args = parser.parse_args()
    
    if args.test_load:
        model, ckpt = load_model(args.test_load)
        print("Model loaded successfully!")
        print(f"Model: {model}")