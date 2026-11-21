
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split


class MyDataset(Dataset):
    def __init__(self, x, y):

        self.x = torch.as_tensor(
            x, dtype=torch.float32
        ).unsqueeze(1)

        y = torch.as_tensor(y)

        # Support both integer labels and one-hot labels
        if y.ndim == 2:
            y = y.argmax(dim=1)

        self.y = y.long()

    def __len__(self):
        return len(self.x)

    def __getitem__(self, idx):
        return self.x[idx], self.y[idx]


def get_dataloaders(X, Y, opt):

    # Convert one-hot labels into integer class labels
    labels = Y.argmax(axis=1) if Y.ndim == 2 else Y

    x_train, x_hold, y_train, y_hold = train_test_split(
        X,
        labels,
        train_size=opt.train_size,
        stratify=labels,
        random_state=42
    )

    x_valid, x_test, y_valid, y_test = train_test_split(
        x_hold,
        y_hold,
        train_size=0.5,
        stratify=y_hold,
        random_state=42
    )

    train_dl = DataLoader(
        MyDataset(x_train, y_train),
        batch_size=opt.batch_size,
        shuffle=True
    )

    valid_dl = DataLoader(
        MyDataset(x_valid, y_valid),
        batch_size=opt.batch_size,
        shuffle=False
    )

    test_dl = DataLoader(
        MyDataset(x_test, y_test),
        batch_size=opt.batch_size,
        shuffle=False
    )

    return train_dl, valid_dl, test_dl
