import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split


class SignalDataset(Dataset):
    """
    Dataset for 1D signal classification.
    
    Keeps data on CPU in __getitem__ for better DataLoader performance.
    Device transfer happens in the training loop.
    """
    def __init__(self, x, y):
        # x shape: (N, window_size) -> (N, 1, window_size) for Conv1d
        self.x = torch.tensor(x, dtype=torch.float32).unsqueeze(1)
        # y shape: (N, num_classes) one-hot -> (N,) class indices
        self.y = torch.argmax(torch.tensor(y, dtype=torch.float32), dim=1).long()

    def __len__(self):
        return len(self.x)

    def __getitem__(self, idx):
        return self.x[idx], self.y[idx]


def get_dataloaders(X, Y, opt):
    """
    Create train/validation/test data loaders.
    
    Args:
        X: Input signals (N, window_size)
        Y: One-hot labels (N, num_classes)
        opt: Options with train_size, batch_size
        
    Returns:
        train_dl, valid_dl, test_dl
    """
    # Split: train / (valid + test)
    x_train, x_temp, y_train, y_temp = train_test_split(
        X, Y, train_size=opt.train_size, stratify=Y, random_state=42
    )
    
    # Split temp: valid / test (50/50)
    x_valid, x_test, y_valid, y_test = train_test_split(
        x_temp, y_temp, train_size=0.5, stratify=y_temp, random_state=42
    )

    print(f"Data splits:")
    print(f"  Train: {len(x_train)} samples")
    print(f"  Valid: {len(x_valid)} samples")
    print(f"  Test:  {len(x_test)} samples")

    train_ds = SignalDataset(x_train, y_train)
    valid_ds = SignalDataset(x_valid, y_valid)
    test_ds = SignalDataset(x_test, y_test)

    train_dl = DataLoader(train_ds, batch_size=opt.batch_size, shuffle=True, 
                          num_workers=0, pin_memory=True)
    valid_dl = DataLoader(valid_ds, batch_size=opt.batch_size, shuffle=False,
                          num_workers=0, pin_memory=True)
    test_dl = DataLoader(test_ds, batch_size=opt.batch_size, shuffle=False,
                         num_workers=0, pin_memory=True)
    
    return train_dl, valid_dl, test_dl


if __name__ == "__main__":
    # Test dataset creation
    import numpy as np
    from arguments import get_args
    
    # Dummy data
    X = np.random.randn(1000, 1200)
    Y = np.zeros((1000, 4))
    for i in range(4):
        Y[i*250:(i+1)*250, i] = 1
    
    class Opt:
        train_size = 0.8
        batch_size = 64
    
    train_dl, valid_dl, test_dl = get_dataloaders(X, Y, Opt())
    
    print(f"\nTrain batches: {len(train_dl)}")
    print(f"Valid batches: {len(valid_dl)}")
    print(f"Test batches: {len(test_dl)}")
    
    # Test one batch
    for x, y in train_dl:
        print(f"Batch x shape: {x.shape}")  # Should be (batch_size, 1, 1200)
        print(f"Batch y shape: {y.shape}")  # Should be (batch_size,)
        break