import copy
import numpy as np
import torch
from tqdm import tqdm
from model import CNNModel

def train_model(opt, train_dl, valid_dl, num_classes=4):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CNNModel(num_classes=num_classes).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=opt.lr)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lr_lambda=lambda epoch: opt.lamda ** epoch
    )
    criterion = torch.nn.CrossEntropyLoss()

    history = {
        "train_loss": [], "valid_loss": [],
        "train_accuracy": [], "valid_accuracy": [],
        "learning_rate": [], "best_epoch": 0
    }
    best_loss = float("inf")
    best_state = None
    patience_count = 0

    for epoch in tqdm(range(opt.epochs), desc="Training"):
        model.train()
        train_losses, train_correct, train_total = [], 0, 0
        for x, y in train_dl:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()

            train_losses.append(loss.item())
            train_correct += (logits.argmax(1) == y).sum().item()
            train_total += y.size(0)

        model.eval()
        valid_losses, valid_correct, valid_total = [], 0, 0
        with torch.no_grad():
            for x, y in valid_dl:
                x, y = x.to(device), y.to(device)
                logits = model(x)
                valid_losses.append(criterion(logits, y).item())
                valid_correct += (logits.argmax(1) == y).sum().item()
                valid_total += y.size(0)

        train_loss = float(np.mean(train_losses))
        valid_loss = float(np.mean(valid_losses))
        history["train_loss"].append(train_loss)
        history["valid_loss"].append(valid_loss)
        history["train_accuracy"].append(100.0 * train_correct / max(train_total, 1))
        history["valid_accuracy"].append(100.0 * valid_correct / max(valid_total, 1))
        history["learning_rate"].append(optimizer.param_groups[0]["lr"])

        if valid_loss < best_loss:
            best_loss = valid_loss
            patience_count = 0
            history["best_epoch"] = epoch + 1
            best_state = copy.deepcopy(model.state_dict())
        else:
            patience_count += 1
            if patience_count >= opt.early_stop:
                print(f"Early stopping at epoch {epoch + 1}")
                break

        scheduler.step()

    if best_state is None:
        raise RuntimeError("Training did not produce a valid checkpoint.")
    model.load_state_dict(best_state)
    return model, history
