import math
import torch
import torch.nn as nn
from torch._tensor import Tensor
from bcnn.conv import BinaryConv2dEODLA


# %% Model definition
class BinaryCNNSingleBin(nn.Module):
    def __init__(
        self, 
        channels: int = 8,
        eodla: bool = False, 
        translator: nn.Module | None = None, 
        optics_sim: nn.Module | None = None,
        device: torch.device | None = None
        ) -> None:
        super(BinaryCNNSingleBin, self).__init__()
        '''
        Binary CNN for EMNIST Digits vs Letters classification.
        Same architecture as FaceNotFace version - 3 binary conv layers with skip connections.
        '''
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.device = device

        # First binary convolutional layer
        self.conv1 = BinaryConv2dEODLA(
            in_channels=3, 
            out_channels=channels, 
            kernel_size=9, 
            dropout_ratio=0.01, 
            bias=True, 
            eodla=eodla, 
            translator=translator,
            optics_sim=optics_sim,
            device=self.device, 
        )
        
        # Conventional convolutional layer to reduce spatial dimensions
        self.conv2 = nn.Conv2d(
            in_channels=channels, 
            out_channels=1, 
            kernel_size=3,
            stride=2,
            padding=1,
        )

        # Max Pooling layer
        self.maxpool = nn.MaxPool2d(2)

        # Predefined masks for classification
        # digit_mask: top-heavy pattern for digits
        # letter_mask: bottom-heavy pattern for letters
        self.digit_mask = self.create_digit_mask()
        self.letter_mask = self.create_letter_mask()
        self.divider = torch.numel(self.digit_mask)  # Normalization factor for scores
        
        # Grab binary layers
        self.binary_conv_layers = [
            module for module in self.modules() if isinstance(module, BinaryConv2dEODLA)
        ]

    def create_digit_mask(self) -> Tensor:
        """Mask that rewards top-heavy activations (for digits)"""
        mask = torch.ones(1, 1, 4, 4, device=self.device)
        mask[:, :, :2, :] = 2
        mask[:, :, 2:, :] = -1
        return mask

    def create_letter_mask(self) -> Tensor:
        """Mask that rewards bottom-heavy activations (for letters)"""
        mask = torch.ones(1, 1, 4, 4, device=self.device)
        mask[:, :, :2, :] = -1
        mask[:, :, 2:, :] = 2
        return mask

    def forward(self, x: Tensor) -> tuple[Tensor, list[Tensor]]:
        # First binary conv layer
        x1 = self.conv1(x)
        
        x2 = self.conv2(x1)

        # Max Pooling
        x_pooled = self.maxpool(x2)

        # Process output using masks
        digit_score = torch.sum(x_pooled * self.digit_mask, dim=(1, 2, 3)) / self.divider
        letter_score = torch.sum(x_pooled * self.letter_mask, dim=(1, 2, 3)) / self.divider
        classification = torch.stack([digit_score, letter_score], dim=1)
        
        return classification, [x1, x2, x_pooled]
    