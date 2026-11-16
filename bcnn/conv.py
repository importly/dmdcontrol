from typing import Literal, Tuple
import numpy as np
import torch
from torch import Tensor, zeros
from torch.nn.modules.utils import _pair
from torch.nn import functional as F, Parameter, BatchNorm2d, Dropout, modules
from torch.types import _int, _size
from torch.autograd import Function

from dmdcontrol.laser import Laser
from dmdcontrol.runtime import PairRig
from dmdcontrol.runtime.dmd_conv import combine
from dmdcontrol.runtime.output_grid import Grid, region16
from dmdcontrol.utils.stop import install as stop_on_signals
from metrics import r as pearson, ssim
from replay import capture


# %% Functions for the binary convolution
class BinActive(Function):
    @staticmethod
    def forward(ctx : FunctionCtx, input: Tensor) -> Tensor:
        '''
        Implements a binary activation layer for performing convolutions with bitcount operations.

        ### Parameters
        - input: The input tensor.

        ### Returns
        - input: The sign of the input, which is a simplified representation of the that is needed
                    to perform convolution.
        '''
        # Convolving a weight filter, W, with an input tensor, X, involves computing a scaling factor
        # for all possible sub-tensors in the input with the same size as the weight filter.  Due to
        # overlaps between sub-tensors, finding this scaling factor β for all possible sub-tensors
        # leads to a very large number of redundant computations.  To avoid this unnecessary
        # computation, we can compute a matrix, A, that is the average over absolute values of the
        # elements of the input across the channel.  We can then convolve that matrix, A, with a
        # filter, k, K = A * k, where that filter k contains scaling factors β for all sub-tensors
        # in the input.  Once we obtain the scaling factors for the weights, α, and the input sub-
        # tensors, β, then we can approximate the convolution between the input and the weight
        # filters by binary operations: X * W ≈ (sign(X) * sign (W)) x αK.
        # Technically, BinActive should also be computing A - the average of each input with its
        # neighboring elements.  However, computing this average tends to be very slow.  It also
        # doesn’t seem to impact network accuracy much.  Due to these two reasons, it can be ignored
        # and convolution can be further approximated as: X * W ≈ (sign(X) * sign (W)) x αI, where I
        # is an appropriately sized matrix of ones.  Here, and above, * is XNOR-based convolution
        # and x is the element-wise dot product.
        ctx.save_for_backward(input)
        input = input.sign()

        return input

    @staticmethod
    def backward(ctx : FunctionCtx, *grad_outputs: Tensor) -> Tensor:
        grad_output = grad_outputs[0]
        input, = ctx.saved_tensors # pyright: ignore[reportAttributeAccessIssue]
        grad_input: Tensor = grad_output.clone()
        grad_input[input.ge(1)] = 0
        grad_input[input.le(-1)] = 0
        return grad_input
    
# %%
class BinaryConv2dEODLA(modules.conv._ConvNd):
    def __init__(
        self, 
        in_channels : int, 
        out_channels : int, 
        kernel_size : int = 1, 
        stride : Tuple[float, ...] | float = 1, 
        padding : int = 0, 
        groups : int = 1, 
        bias : bool = True, 
        dropout_ratio : float = 0, 
        dilation : int = 1, 
        padding_mode : Literal['zeros', 'reflect', 'replicate', 'circular'] = 'zeros', 
        device : torch.device | None = None, 
        dtype : torch.dtype = torch.float32, 
        eodla : bool = False, 
        translator : nn.Module | None = None,
        optics_sim : nn.Module | None = None,
        ) -> None:
        '''
        A binary convolutional layer, with the convolution done on EODLA.  Due to the unique properties of this layer, the forward propagation of data is specified.  Additionally, how to update the gradient for this layer is specified.

        ### Parameters
        - in_channels: The number of input channels to the convolutional layer.
        - out_channels: The number of output channels for the convolutional layer.
        - kernel_size: The size of the convolutional filter in each dimension.
        - stride: The convolutional stride.
        - padding: The amount of padding that will be applied to all sides of the input feature map when convolution is performed.
        - groups: The number of blocked connections from input channels to output channels.
        - bias: A binary flag to determine if the layer will learn an additive bias.
        - dropout_ratio: The probability that a given output from the layer will be ignored, thereby performing dropout-based regularization.
        - padding_mode: The type of padding to use for the convolutional layer.
        - device: The device to use for the convolutional layer.
        - dtype: The data type to use for the convolutional layer.
        - eodla: Either the DMD device object or None if it is going to be run on the GPU.
        - translator: A translator model to use for the convolutional layer, or None if it is going to be run on the GPU.
        - optics_sim: An optics simulation model to use for the convolutional layer, or None if it is going to be run on the GPU.
        '''
        if device is None:
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.device = device
            
        # set up variables for ConvNd
        factory_kwargs = {'device': device, 'dtype': dtype}
        kernel_size_ = _pair(kernel_size)
        stride_ = _pair(1)
        padding_ = padding if isinstance(padding, str) else _pair(padding)
        dilation_ = _pair(dilation)
        super(BinaryConv2dEODLA, self).__init__(in_channels, out_channels, kernel_size_, stride_, padding_, dilation_, False, _pair(0), groups, bias, padding_mode, **factory_kwargs)

        if isinstance(stride, tuple):
            self.stride_factor = [1 / s for s in stride]
        else:
            self.stride_factor = [1 / stride, 1 / stride]

        # Specify the convolution operations, the weight initialization, and the bias.
        self.weight.data.normal_(0, 0.05)
        if bias:
            self.bias.data.zero_() # pyright: ignore
        self.fp_weights : Parameter = Parameter(zeros(self.weight.size()))
        self.fp_weights.data.copy_(self.weight.data)
        self.mean_val : Tensor = zeros(self.out_channels)
        
        self.eodla = eodla

        # Translator, make sure params are fixed
        if translator is not None:
            self.translator = translator
            for param in self.translator.parameters():
                param.requires_grad = False
        else:
            self.translator = None
        
        # optics sim
        if optics_sim is not None:
            self.optics_sim = optics_sim
        else:
            self.optics_sim = None

        # Dropout, batch normalization, and binarization
        self.dropout = dropout_ratio
        self.a_active = BinActive.apply
        self.bn = BatchNorm2d(in_channels, track_running_stats=False, affine=False, device=device)
        if(self.dropout != 0): self.drop = Dropout(self.dropout, inplace = True)

    def forward(self, x: Tensor) -> Tensor:
        '''
        Performs some pre-processing to help stabilize feature learning, binarizes the feature maps and kernels, then runs data through EODLA or local machine.

        ### Parameters
        - x: The input tensor to be propagated through a given layer.

        ### Returns
        - x: The transformed tensor after batch normalization, dropout, and convolution are applied.
        '''
        # Save size for later
        input_size = x.size()
        
        # Apply stride to the input tensor, if the stride is not equal to 1.
        # This is implemented via scaling the input tensor where the scaling factor is equal to 1/stride.
        if self.stride_factor != [1, 1]:
            og_size = x.size()[2:]
            x = F.interpolate(x, scale_factor=self.stride_factor, mode='bilinear', align_corners=False)
        
        # Apply batch normalization and binarization to the input tensor. Dropout is also applied if specified.
        x = self.bn(x)
        active_out = self.a_active(x)
        if not isinstance(active_out, Tensor):
            raise TypeError("BinActive.apply must return a Tensor")
        x = active_out
        if(self.dropout != 0): x = self.drop(x)

        # Clamp the weights to be either +1 or -1.
        self.fp_weights.data.clamp_(-1, 1)

        # Get the mean of the weights, assuming that their signs are ignored.  If we do not ignore
        # the weight signs, then the L1 weight norm, computed in the next step, will be incorrect.
        self.mean_val = self.fp_weights.abs().view(self.out_channels, -1).mean(1, keepdim = True)

        # Compute the scaling factor, α, which is the L1 norm of the weights that is normalized
        # by the number of entries.  To do this, we'll use mean_val and then ensure that the weight
        # signs are consistent.  Once this is done, we have found a binarized representation of the
        # weights that is an optimal respresentation of some real-valued weight matrix.  We can then
        # convolve with the input tensor.
        # Since convolution is associative, we'll multiply the α at the end.
        self.weight.data.copy_(self.fp_weights.data.sign())
        
        # Perform the convolution operation, either on EODLA or on the local machine.
        if self.eodla:
            y = self.eodla_conv(x)
            
        elif self.translator:
            y = self.trans_conv(x)
        
        elif self.optics_sim:
            y = self.optic_conv(x)

        else:
            y = F.conv2d(
                input=x, 
                weight=self.weight, 
                bias=self.bias, 
                stride=self.stride, 
                padding='same', 
                dilation=self.dilation, 
                groups=self.groups,
            )
            
        # Now we apply the α
        y = y * self.mean_val.view(1, -1, 1, 1)
        
        if self.stride_factor != [1, 1]:
            y = F.interpolate(y, size=og_size, mode='bilinear', align_corners=False)
        return y

    def update_gradient(self) -> None:
        '''
        Performs a backwards pass, and hence a gradient update, for a given convolutional layer in
        the binary convolutional network.
        '''

        # Similar to the binarization in the forward pass, we can binarize the backwards pass and
        # thus represent training using binary operations.  We estimate two terms to do this,
        # binary_grad and mean_grad.
        # For the former, we multiply three terms: the gradient of the cost function with respect to
        # the binary weights, W', the gradient of the sign of the binary weights, W', with respect
        # to the weights, and α, the optimal scaling factor.  Here, we compute a proxy for α.
        proxy = self.fp_weights.abs().sign()
        proxy[self.fp_weights.data.abs() > 1] = 0
        binary_grad = self.weight.grad * self.mean_val.view(-1, 1, 1, 1) * proxy # pyright: ignore
        
        # The latter relies on two terms: the element-normalized sign of the filter matrix, W, and
        # the sum of the gradients modulated by the sign of the filter matrix, W.  In the first step
        # we compute the sign of the real-valued weights times the gradient of the cost function
        # with respect to the binary weights.  Next, we sum and normalize by the number of elements.
        # Then, we multiply again by the sign of the real-valued weights.
        mean_grad = self.weight.data.sign() * self.weight.grad # pyright: ignore
        mean_grad = mean_grad.view(self.out_channels, -1).mean(1).view(-1, 1, 1, 1)
        mean_grad = mean_grad * self.weight.data.sign()

        # We can sum the two gradient components and weight them.  Note that this is the correct
        # form of the gradient-based update, as it is respect to the sum over all of the elements.
        self.fp_weights.grad = binary_grad + mean_grad

    def eodla_conv(
        self,
        x: Tensor, 
        ) -> Tensor:
        '''
        A 2D convolution, with the convolution simulated through the optical simulation module.
        
        ### Parameters
        - x: input tensor of shape `(minibatch, in_channels, iH , iW)`
        
        ### Returns
        - output (Tensor): binary convolution result
        '''
        B, C, H, W = x.size()
        O, channels_per_group, K, K2 = self.weight.size()
        if K != K2:
            raise ValueError('Only square kernels are supported')
        if C != self.in_channels:
            raise ValueError('Input channel count does not match the layer')
        if C % self.groups != 0 or O % self.groups != 0:
            raise ValueError('in_channels and out_channels must be divisible by groups')
        if channels_per_group != C // self.groups:
            raise ValueError('weight shape does not match the configured groups')

        outputs_per_group = O // self.groups
        # Keep the group and local-channel axes separate so each output only
        # receives inputs from its own group.
        conv2d = torch.empty(
            [B, self.groups, outputs_per_group, channels_per_group, H, W],
            device=x.device,
            dtype=x.dtype,
        )

        for group in range(self.groups):
            input_start = group * channels_per_group
            output_start = group * outputs_per_group
            for output_offset in range(outputs_per_group):
                output_channel = output_start + output_offset
                for input_offset in range(channels_per_group):
                    input_channel = input_start + input_offset
                    
                    # switch this with eodla code
                    conv2d_per_channel = self.optics_sim(
                        x[:, input_channel:input_channel + 1, :, :],
                        self.weight[output_channel:output_channel + 1, input_offset:input_offset + 1, :, :],
                    ) # pyright: ignore
                    
                    
                    
                    if conv2d_per_channel.ndim == 3:
                        conv2d_per_channel = conv2d_per_channel.unsqueeze(1)
                    conv2d[:, group, output_offset, input_offset, :, :] = conv2d_per_channel.squeeze(1)

        conv2d = conv2d.sum(dim=3).reshape(B, O, H, W)
        conv2d = conv2d + self.bias.view(1, -1, 1, 1) if self.bias is not None else conv2d
        
        return conv2d
    
    def trans_conv(
        self,
        x: Tensor, 
        ) -> Tensor:
        '''
        A 2D convolution, with the convolution translated to the optical respresentation with the translator model.
        
        ### Parameters
        - x: input tensor of shape `(minibatch, in_channels, iH , iW)`
        
        ### Returns
        - output (Tensor): binary convolution result
        '''
        B, C, H, W = x.size()
        O, channels_per_group, K, K2 = self.weight.size()
        assert K == K2
        if C % self.groups != 0 or O % self.groups != 0:
            raise ValueError('in_channels and out_channels must be divisible by groups')
        if channels_per_group != C // self.groups:
            raise ValueError('weight shape does not match the configured groups')

        outputs_per_group = O // self.groups
        
        pad = K // 2  # for 9x9 kernel, this is 4
        
        # Calculate 'same' padding
        padded = F.pad(x, (pad, pad, pad, pad), mode='constant', value=0.0)
    
        # Conv patches: [B, C*K*K, H*W] => [B, H*W, C, K*K]
        x_unf = F.unfold(padded, kernel_size=K, stride=1, padding=0)
        x_unf = x_unf.view(B, C, K * K, H*W).permute(0, 3, 1, 2)
    
        # Contract only input channels that belong to the same group.
        # Keeping the group axis makes the channel connectivity explicit.
        x_grouped = x_unf.view(B, H * W, self.groups, channels_per_group, K * K)
        w_grouped = self.weight.view(
            self.groups, outputs_per_group, channels_per_group, K * K
        )
        pair = torch.einsum('blgcp,gocp->bgolc', x_grouped, w_grouped)

        # Translate every connected pair in one batched call, then sum the
        # input-channel axis within each group.
        translator_input = pair.permute(0, 1, 2, 4, 3).reshape(
            B * self.groups * outputs_per_group * channels_per_group, 1, H, W
        )
        translated = self.translator(translator_input) # pyright: ignore
        translated = translated.reshape(
            B, self.groups, outputs_per_group, channels_per_group, H, W
        )
        conv2d = translated.sum(dim=3).reshape(B, O, H, W)

        conv2d = conv2d + self.bias.view(1, -1, 1, 1) if self.bias is not None else conv2d
        
        return conv2d
                
    def optic_conv(
        self,
        x: Tensor, 
        ) -> Tensor:
        '''
        A 2D convolution, with the convolution simulated through the optical simulation module.
        
        ### Parameters
        - x: input tensor of shape `(minibatch, in_channels, iH , iW)`
        
        ### Returns
        - output (Tensor): binary convolution result
        '''
        B, C, H, W = x.size()
        O, channels_per_group, K, K2 = self.weight.size()
        if K != K2:
            raise ValueError('Only square kernels are supported')
        if C != self.in_channels:
            raise ValueError('Input channel count does not match the layer')
        if C % self.groups != 0 or O % self.groups != 0:
            raise ValueError('in_channels and out_channels must be divisible by groups')
        if channels_per_group != C // self.groups:
            raise ValueError('weight shape does not match the configured groups')

        outputs_per_group = O // self.groups
        # Keep the group and local-channel axes separate so each output only
        # receives inputs from its own group.
        conv2d = torch.empty(
            [B, self.groups, outputs_per_group, channels_per_group, H, W],
            device=x.device,
            dtype=x.dtype,
        )
        for group in range(self.groups):
            input_start = group * channels_per_group
            output_start = group * outputs_per_group
            for output_offset in range(outputs_per_group):
                output_channel = output_start + output_offset
                for input_offset in range(channels_per_group):
                    input_channel = input_start + input_offset
                    conv2d_per_channel, _ = self.optics_sim(
                        x[:, input_channel:input_channel + 1, :, :],
                        self.weight[output_channel:output_channel + 1, input_offset:input_offset + 1, :, :],
                    ) # pyright: ignore
                    if conv2d_per_channel.ndim == 3:
                        conv2d_per_channel = conv2d_per_channel.unsqueeze(1)
                    conv2d_per_channel = F.interpolate(
                        conv2d_per_channel,
                        size=(H, W),
                        mode='bilinear',
                        align_corners=False,
                    )
                    conv2d[:, group, output_offset, input_offset, :, :] = conv2d_per_channel.squeeze(1)

        conv2d = conv2d.sum(dim=3).reshape(B, O, H, W)
        conv2d = conv2d + self.bias.view(1, -1, 1, 1) if self.bias is not None else conv2d
        
        return conv2d