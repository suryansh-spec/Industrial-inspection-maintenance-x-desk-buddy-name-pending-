"""Extensive 1D CNN for bearing fault classification.

Architecture highlights:
  * 6 residual conv blocks with squeeze-and-excitation (SE) attention
  * Multi-axis input support (1 channel = single axis, 3 channels = x/y/z)
  * Global average pooling + classifier head with dropout
  * Two model variants: ``extensive`` (full server model) and ``light`` (edge-ready)
  * Optional spectral pre-processing branch (FFT magnitude concatenated)

Expected input: ``(batch, channels, window_size)`` where ``window_size`` is
typically 1024–4096 samples at 12 kHz.
"""

from __future__ import annotations

import math
import torch
import torch.nn as nn
import torch.nn.functional as F


class SEBlock1d(nn.Module):
    """Squeeze-and-Excitation channel attention for 1D feature maps."""

    def __init__(self, channels: int, reduction: int = 16):
        super().__init__()
        reduced = max(4, channels // reduction)
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Conv1d(channels, reduced, 1),
            nn.ReLU(inplace=True),
            nn.Conv1d(reduced, channels, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.se(x)


class ResidualConvBlock1d(nn.Module):
    """Residual block: Conv -> BN -> ReLU -> Conv -> BN -> SE -> +skip -> ReLU."""

    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        kernel_size: int = 3,
        stride: int = 1,
        dilation: int = 1,
        dropout: float = 0.1,
        use_se: bool = True,
    ):
        super().__init__()
        padding = (kernel_size - 1) // 2 * dilation
        self.conv1 = nn.Conv1d(
            in_ch, out_ch, kernel_size, stride=stride,
            padding=padding, dilation=dilation, bias=False,
        )
        self.bn1 = nn.BatchNorm1d(out_ch)
        self.conv2 = nn.Conv1d(
            out_ch, out_ch, kernel_size, stride=1,
            padding=padding, dilation=dilation, bias=False,
        )
        self.bn2 = nn.BatchNorm1d(out_ch)
        self.se = SEBlock1d(out_ch) if use_se else nn.Identity()
        self.dropout = nn.Dropout(dropout)

        self.skip = nn.Identity()
        if stride != 1 or in_ch != out_ch:
            self.skip = nn.Sequential(
                nn.Conv1d(in_ch, out_ch, 1, stride=stride, bias=False),
                nn.BatchNorm1d(out_ch),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = self.skip(x)
        out = self.conv1(x)
        out = self.bn1(out)
        out = F.relu(out, inplace=True)
        out = self.dropout(out)
        out = self.conv2(out)
        out = self.bn2(out)
        out = self.se(out)
        out = out + identity
        out = F.relu(out, inplace=True)
        return out


class ExtensiveCNN(nn.Module):
    """Deep residual 1D CNN for bearing fault classification.

    Parameters
    ----------
    num_classes : int
        Number of fault classes (default 4: Normal, Inner, Ball, Outer).
    in_channels : int
        Number of input signal channels (1 = single axis, 3 = x/y/z).
    variant : str
        ``"extensive"`` for the full server model, ``"light"`` for edge.
    window_size : int
        Length of the input vibration window in samples.
    dropout : float
        Dropout probability in the classifier head.
    use_spectral : bool
        If True, concatenate a branch that processes the FFT magnitude.
    """

    def __init__(
        self,
        num_classes: int = 4,
        in_channels: int = 1,
        variant: str = "extensive",
        window_size: int = 2048,
        dropout: float = 0.3,
        use_spectral: bool = False,
    ):
        super().__init__()
        self.num_classes = num_classes
        self.in_channels = in_channels
        self.window_size = window_size
        self.use_spectral = use_spectral

        # Stage definitions: (in_ch, out_ch, stride, dilation, repeats, use_se)
        if variant == "light":
            stages = [
                (in_channels, 32, 1, 1, 2, True),
                (32, 64, 2, 1, 2, True),
                (64, 128, 2, 2, 2, True),
                (128, 256, 2, 2, 2, True),
            ]
            head_hidden = 256
        else:  # "extensive"
            stages = [
                (in_channels, 64, 1, 1, 2, True),
                (64, 128, 2, 1, 3, True),
                (128, 256, 2, 2, 3, True),
                (256, 512, 2, 2, 3, True),
                (512, 512, 2, 4, 2, True),
            ]
            head_hidden = 512

        # Build encoder
        layers: list[nn.Module] = []
        in_ch = in_channels
        for stage_in, stage_out, stride, dilation, repeats, use_se in stages:
            for i in range(repeats):
                s = stride if i == 0 else 1
                d = dilation
                layers.append(
                    ResidualConvBlock1d(
                        in_ch, stage_out,
                        kernel_size=3, stride=s, dilation=d,
                        dropout=dropout * 0.5, use_se=use_se,
                    )
                )
                in_ch = stage_out

        self.encoder = nn.Sequential(*layers)
        self.encoder_out_ch = in_ch

        # Spectral branch (FFT magnitude processed by a small conv stack)
        self.use_spectral = use_spectral and in_channels >= 1
        if self.use_spectral:
            self.spec_conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, 7, padding=3),
                nn.BatchNorm1d(32),
                nn.ReLU(inplace=True),
                nn.MaxPool1d(2),
                nn.Conv1d(32, 64, 5, padding=2),
                nn.BatchNorm1d(64),
                nn.ReLU(inplace=True),
                nn.AdaptiveAvgPool1d(1),
                nn.Flatten(),
            )
            head_hidden += 64

        # Classifier head input dimension depends on spectral branch
        classifier_in_ch = self.encoder_out_ch + (64 if self.use_spectral else 0)

        self.global_pool = nn.AdaptiveAvgPool1d(1)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.BatchNorm1d(classifier_in_ch),
            nn.Dropout(dropout),
            nn.Linear(classifier_in_ch, head_hidden),
            nn.BatchNorm1d(head_hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(head_hidden, head_hidden // 2),
            nn.BatchNorm1d(head_hidden // 2),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout * 0.5),
            nn.Linear(head_hidden // 2, num_classes),
        )

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, channels, window_size)"""
        features = self.encoder(x)          # (batch, C, T')
        features = self.global_pool(features)  # (batch, C, 1)

        if self.use_spectral:
            # Compute FFT magnitude along the time axis
            x_fft = torch.fft.rfft(x, dim=-1)
            x_mag = torch.abs(x_fft)        # (batch, channels, freq_bins)
            spec_feat = self.spec_conv(x_mag)  # (batch, 64)
            time_feat = features.squeeze(-1)   # (batch, C)
            combined = torch.cat([time_feat, spec_feat], dim=-1)
        else:
            combined = features.squeeze(-1)    # (batch, C)

        logits = self.classifier(combined)
        return logits


def create_model(
    num_classes: int = 4,
    in_channels: int = 1,
    variant: str = "extensive",
    window_size: int = 2048,
    dropout: float = 0.3,
    use_spectral: bool = False,
) -> ExtensiveCNN:
    """Factory function for the bearing fault CNN."""
    return ExtensiveCNN(
        num_classes=num_classes,
        in_channels=in_channels,
        variant=variant,
        window_size=window_size,
        dropout=dropout,
        use_spectral=use_spectral,
    )


if __name__ == "__main__":
    import torch
    model = create_model(variant="extensive", in_channels=3, window_size=2048, use_spectral=True)
    dummy = torch.randn(4, 3, 2048)
    out = model(dummy)
    print(f"Input: {dummy.shape} -> Output: {out.shape}")
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {total_params:,}")
