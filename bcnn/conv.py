from pathlib import Path
from typing import Optional, Union
import numpy as np    
import torch
from torch import Tensor, zeros
from torch.nn.modules.utils import _pair
from torch.nn import functional as F, grad as G, Parameter, BatchNorm2d, Dropout, modules
from torch.types import _int, _size
from torch.autograd import Function
from dmdcontrol.dmd_conv import dmd_conv

# %% Functions for the binary convolution
class BinActive(Function):
    @staticmethod
    def forward(ctx, input):
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
    def backward(ctx, grad_output):
        input, = ctx.saved_tensors
        grad_input = grad_output.clone()
        grad_input[input.ge(1)] = 0
        grad_input[input.le(-1)] = 0
        return grad_input
    
# %%
class Conv2dEODLA(Function):
    @staticmethod
    def forward(ctx, input: Tensor, weight: Tensor, bias: Optional[Tensor]=None, stride: Union[_int, _size]=1, padding: Union[_int, _size]=0, dilation: Union[_int, _size]=1, groups: _int=1, eodla: bool=True, out_channels = 1, run_dir: Path | None=None) -> Tensor:
        '''
        ******** Change this function so that out_channels is accounted for******** (currently it's 128, want to make it variable)        ****DONE****
        A 2D convolution, with the convolution done on EODLA or software.

        ### Parameters
        - input: input tensor of shape `(minibatch, in_channels, iH , iW)`
        - weight: filters of shape `(out_channels, in_channels/groups, kH , kW)`
        - bias: optional bias tensor of shape `(out_channels)`.
                - Default: ``None``
        - stride: the stride of the convolving kernel. Can be a single number or a tuple `(sH, sW)`. 
            - Default: 1
        - padding: `NOTE: not implemented yet!` implicit paddings on both sides of the input. Can be a string {'valid', 'same'}, single number or a tuple `(padH, padW)`. 
                - Default: 0
                - ``padding='valid'`` is the same as no padding. 
                - ``padding='same'`` pads the input so the output has the shape as the input.However, this mode doesn't support any stride values other than 1.
        - dilation: the spacing between kernel elements. Can be a single number or a tuple `(dH, dW)`.
                - Default: 1
        - groups: split input into groups, `in_channels` should be divisible by the number of groups. 
                - Default: 1
        - dmd_device: The DMD device object to use for the convolution, or None if it is going to be run on the GPU.
        - eodla: A binary flag to determine if the layer will be run on EODLA.

        ### Returns
        - output (Tensor): binary convolution result
        '''

        if eodla:
            # send data to EODLA and receive result from EODLA
            if weight.is_cuda:
                temp_kernel = weight.data.detach().clone().cpu()
                temp_fm = input.detach().clone().cpu()
            else:
                temp_kernel = weight.data.detach().clone()
                temp_fm = input.detach().clone()

            # make dmd sized kernel and feature map
            temp_kernel = torch.nn.functional.interpolate(temp_kernel, size=(168, 168), mode='nearest', align_corners=None).numpy()
            temp_fm = torch.nn.functional.interpolate(temp_fm, size=(300, 300), mode='nearest', align_corners=None).numpy()

            eodla_output = torch.empty([temp_fm.shape[0], out_channels, temp_fm.shape[1], 60, 60])
            for in_ch in range(temp_kernel.shape[1]):
                for out_ch in range(temp_kernel.shape[0]):
                    eodla_output[:, out_ch, in_ch, :, :] = torch.from_numpy(
                        dmd_conv(
                            k=temp_kernel[out_ch, in_ch], 
                            fm=temp_fm[:, in_ch],
                            save_sheet=True if np.random.randint(0, 1000) < 10 else False,
                            run_dir=run_dir,
                        )
                    ).float().to(weight.device)
            
            output = eodla_output.sum(axis=2)

            # scale the data to match the gpu
            # output = output * 2

            if bias is not None:
                output += bias[None, :, None, None]

            ctx.save_for_backward(input, weight, bias)
            ctx.stride = stride
            ctx.padding = padding 
            ctx.dilation = dilation
            ctx.groups = groups
            ctx.eodla = eodla
            return output.to(weight.device)

        else:
            output = F.conv2d(input=input, weight=weight, bias=bias,
                                 stride=stride, dilation=dilation, groups=groups)
            
            ctx.save_for_backward(input, weight, bias)
            ctx.stride = stride
            ctx.padding = padding 
            ctx.dilation = dilation
            ctx.groups = groups
            ctx.eodla = eodla
            return output
            
    @staticmethod
    def backward(ctx, grad_output):
        '''
        Here we perform the backward pass for a 2D convolution manually. This is done to ensure that the data used corresponds to the device used (EODLA, PC).
        '''
        input, weight, bias = ctx.saved_tensors
        stride = ctx.stride
        padding = ctx.padding 
        dilation = ctx.dilation
        groups = ctx.groups
        eodla = ctx.eodla
        grad_input = grad_weight = grad_bias = None

        if ctx.needs_input_grad[0]:
            if eodla: grad_input = G.conv2d_input(input.shape, weight, grad_output, stride, padding, 1, groups)
            else: grad_input = G.conv2d_input(input.shape, weight, grad_output, stride, 0, dilation, groups)
        if ctx.needs_input_grad[1]:
            if eodla: grad_weight = G.conv2d_weight(input, weight.shape, grad_output, stride, padding, 1, groups) 
            else: grad_weight = G.conv2d_weight(input, weight.shape, grad_output, stride, 0, dilation, groups) 
        if bias is not None and ctx.needs_input_grad[2]:
            grad_bias = grad_output.sum((0,2,3)).squeeze(0)

        return grad_input, grad_weight, grad_bias, None, None, None, None, None, None


# %%
class BinaryConv2dEODLA(modules.conv._ConvNd):
    def __init__(self, in_channels, out_channels, kernel_size = 1, stride = 1, padding = 0, groups = 1, bias = True, dropout_ratio = 0, dilation = 1, port=4040, padding_mode: str = 'zeros', device=None, dtype=None, eodla=None) -> None:
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
        - port: The port to use for the socket connection.
        - padding_mode: The type of padding to use for the convolutional layer.
        - device: The device to use for the convolutional layer.
        - dtype: The data type to use for the convolutional layer.
        - eodla: Either the DMD device object or None if it is going to be run on the GPU.
        '''
        # set up variables for ConvNd
        factory_kwargs = {'device': device, 'dtype': dtype}
        kernel_size_ = _pair(kernel_size)
        stride_ = _pair(stride)
        padding_ = padding if isinstance(padding, str) else _pair(padding)
        dilation_ = _pair(dilation)
        super(BinaryConv2dEODLA, self).__init__(in_channels, out_channels, kernel_size_, stride_, padding_, dilation_, False, _pair(0), groups, bias, padding_mode, **factory_kwargs)

        # Specify the convolution operations, the weight initialization, and the bias.
        self.weight.data.normal_(0, 0.05) # 0.05
        if bias:
            self.bias.data.zero_()
        self.fp_weights = Parameter(zeros(self.weight.size()))
        self.fp_weights.data.copy_(self.weight.data)

        # Set up the DMD device, if it is being used.
        if eodla is None:
            self.eodla = False
        else: 
            self.eodla = True

        self.dmd_device = eodla

        # Set the class variables based on the inputs.
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

        # Apply batch normalization and binarization to the input tensor. Dropout is also applied if specified.
        x = self.bn(x)
        x = self.a_active(x)
        if(self.dropout != 0): x = self.drop(x)

        # Compute the weight means and remove them.  This is helpful first step for convolutional
        # networks, especially when pooling is used.
        # More specifically, pooling results in a significant loss of information, especially for
        # binary networks.  Max pooling a binary input, for example, returns a tensor where most of
        # its elements are +1.  For min pooling, most of the responses will be -1.  In either case,
        # we can’t really infer much about the structure of the features, which propagates nonsense
        # through the network.  By normalizing to zero mean, we reduce the quantization error,
        # indicating that more entries have the chance of being -1 and +1, not just one or the
        # other.  This hence yields more meaningful pooling responses as we reduce and transform
        # the features.
        # Commented out: whwen the channel size is small, the mean is close in value to the weight data, driving the weights to zero.
        # if self.fp_weights.size()[0] != 1: self.fp_weights.data = self.fp_weights.data - self.fp_weights.data.mean(1, keepdim = True)

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
        self.weight.data.copy_(self.fp_weights.data.sign() * self.mean_val.view(-1, 1, 1, 1))

        if not self.eodla:
            # pad data
            if self.padding_mode != 'zeros': 
                x = F.pad(x, [pad for pad in self._reversed_padding_repeated_twice], mode=self.padding_mode)
            else:
                x = F.pad(x, [pad for pad in self._reversed_padding_repeated_twice], mode='constant', value=0)

        # Perform the convolution operation, either on EODLA or on the local machine.
        # print(x.shape, self.weight.shape, self.bias.shape)
        conv2d = Conv2dEODLA.apply(x, self.weight, self.bias, self.stride, [4, 4], self.dilation, self.groups, self.dmd_device, self.eodla)
        
        return conv2d

    def update_gradient(self):
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
        binary_grad = self.weight.grad * self.mean_val.view(-1, 1, 1, 1) * proxy
        
        # The latter relies on two terms: the element-normalized sign of the filter matrix, W, and
        # the sum of the gradients modulated by the sign of the filter matrix, W.  In the first step
        # we compute the sign of the real-valued weights times the gradient of the cost function
        # with respect to the binary weights.  Next, we sum and normalize by the number of elements.
        # Then, we multiply again by the sign of the real-valued weights.
        mean_grad = self.weight.data.sign() * self.weight.grad
        mean_grad = mean_grad.view(self.out_channels, -1).mean(1).view(-1, 1, 1, 1)
        mean_grad = mean_grad * self.weight.data.sign()

        # We can sum the two gradient components and weight them.  Note that this is the correct
        # form of the gradient-based update, as it is respect to the sum over all of the elements.
        self.fp_weights.grad = binary_grad + mean_grad
        # multiplying the gradient by a scalar here helps the binary weights change faster. this is useful especially when layers of the model are training way faster than the bconv layers.
        self.fp_weights.grad *= 100
        
        # This is commented out because it was breaking for one output channel
        # if self.fp_weights.size()[1] != 1: self.fp_weights.grad = self.fp_weights.grad * self.fp_weights.data[0].nelement() \
        #                        * (1 - 1/self.fp_weights.data.size(1))
        # else: self.fp_weights.grad = self.fp_weights.grad #* self.fp_weights.data[0].nelement()  
