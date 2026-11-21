"""
CNN Model Definition for Signal Fault Classification.
"""
import torch
import torch.nn as nn
import logging

logger = logging.getLogger(__name__)


class CNNModel(nn.Module):
    """1D CNN for bearing fault classification."""
    
    def __init__(
        self, 
        input_channels: int = 1,
        num_classes: int = 4,
        window_size: int = 1200
    ):
        super().__init__()
        
        self.input_channels = input_channels
        self.num_classes = num_classes
        self.window_size = window_size
        
        # Encoder: 3 Conv blocks
        self.encoder = nn.Sequential(
            # Block 1: (1, 1200) -> (16, 600)
            nn.Conv1d(input_channels, 16, kernel_size=3, padding=1),
            nn.BatchNorm1d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(kernel_size=2),
            
            # Block 2: (16, 600) -> (32, 300)
            nn.Conv1d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(kernel_size=2),
            
            # Block 3: (32, 300) -> (64, 150)
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(kernel_size=2),
            
            nn.Flatten()
        )
        
        # Calculate flattened size: 64 * (window_size / 8) = 64 * 150 = 9600
        self.flattened_size = 64 * (window_size // 8)
        
        # Classifier
        self.predictor = nn.Sequential(
            nn.Linear(self.flattened_size, 1000),
            nn.BatchNorm1d(1000),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            
            nn.Linear(1000, 100),
            nn.BatchNorm1d(100),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            
            nn.Linear(100, num_classes)
        )
        
        # Initialize weights
        self._initialize_weights()
    
    def _initialize_weights(self):
        """Initialize model weights."""
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, 0, 0.01)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass."""
        x = self.encoder(x)
        x = self.predictor(x)
        return x
    
    def get_features(self, x: torch.Tensor) -> torch.Tensor:
        """Extract features from encoder (before classifier)."""
        return self.encoder(x)
    
    def get_num_parameters(self) -> int:
        """Get total number of parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
    
    def get_model_size_mb(self) -> float:
        """Get model size in MB."""
        param_size = sum(p.numel() * p.element_size() for p in self.parameters())
        buffer_size = sum(b.numel() * b.element_size() for b in self.buffers())
        return (param_size + buffer_size) / (1024 * 1024)


def create_model(
    num_classes: int = 4,
    window_size: int = 1200,
    device: str = "auto"
) -> CNNModel:
    """Factory function to create model."""
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    model = CNNModel(num_classes=num_classes, window_size=window_size)
    model = model.to(device)
    
    logger.info(f"Model created on {device}: {model.get_num_parameters():,} parameters, {model.get_model_size_mb():.2f} MB")
    return model


def load_model_from_checkpoint(
    checkpoint_path: str,
    num_classes: int = 4,
    window_size: int = 1200,
    device: str = "auto"
) -> CNNModel:
    """Load model from checkpoint."""
    model = create_model(num_classes, window_size, device)
    
    checkpoint = torch.load(checkpoint_path, map_location=device)
    
    if 'model_state_dict' in checkpoint:
        model.load_state_dict(checkpoint['model_state_dict'])
    else:
        model.load_state_dict(checkpoint)
    
    model.eval()
    logger.info(f"Model loaded from {checkpoint_path}")
    return model