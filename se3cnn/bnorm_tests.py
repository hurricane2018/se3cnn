import unittest, torch
import torch.nn as nn

from batchnorm import SE3BNConvolution, SE3BatchNorm
from convolution import SE3Convolution

class JointConvolution(nn.Module):
    ''' Compose SE3BN with SE3Conv to emulate SE3BNConv '''
    def __init__(self, repr_in, repr_out, size=5):
        super(JointConvolution, self).__init__()

        self.conv = SE3Convolution(repr_in, repr_out, size=size)

        bn_repr = [(m, (2 * j) + 1) for m, j in repr_in]
        self.bn = SE3BatchNorm(bn_repr)

    def forward(self, inp):
        y = self.bn(inp)
        return self.conv(y)

class Tests(unittest.TestCase):
    def _test_equivariance(self, module, cuda=True):
        torch.set_default_dtype(torch.float64)

        io_repr = [(1, 0)]
        mid_repr = [(2, 0), (2, 1), (1, 2)]

        f = torch.nn.Sequential(
            module(io_repr, mid_repr, size=5),
            module(mid_repr, io_repr, size=5),
        )

        def rotate(t):
            # rotate 90 degrees in plane of axes 2 and 3
            return torch.flip(t, (2, )).transpose(2, 3)

        def unrotate(t):
            # undo the rotation by 3 more rotations
            return rotate(rotate(rotate(t)))

        inp = torch.randn(4, 1, 12, 12, 12)

        if cuda:
            f = f.cuda()
            inp = inp.cuda()

        inp_r = rotate(inp)

        diff_inp = (inp - unrotate(inp_r)).abs().max().item()
        self.assertLess(diff_inp, 1e-10) # sanity check

        out = f(inp)
        out_r = f(inp_r)

        diff_out = (out - unrotate(out_r)).abs().max().item()
        self.assertLess(diff_out, 1e-10)

    def test_se3bnconv_equivariance_cuda(self):
        self._test_equivariance(module=SE3BNConvolution, cuda=True)

    def test_se3bnconv_equivariance_cpu(self):
        self._test_equivariance(module=SE3BNConvolution, cuda=False)

    def test_se3bn_equivariance_cuda(self):
        self._test_equivariance(module=JointConvolution, cuda=True)

    def test_se3bn_equivariance_cpu(self):
        self._test_equivariance(module=JointConvolution, cuda=False)

    def test_does_reduce_variance(self):
        Rs_in =[(2, 0), (2, 1), (1, 2), (1, 3)]
        Rs_out = [(2, 0), (2, 1), (1, 2)]
        kernel_size = 5
        batch = 4
        input_size = 10

        # input
        n_out = sum([m * (2 * l + 1) for m, l in Rs_out])
        n_in = sum([m * (2 * l + 1) for m, l in Rs_in])
        x = torch.rand(batch, n_in, input_size, input_size, input_size) * 2 + 2

        # BNConv
        bnconv = SE3BNConvolution(Rs_in, Rs_out, kernel_size)
        bnconv.train()
        y1 = bnconv(x)

        self.assertEqual(y1.size(1), n_out)

        # BN + Conv
        bn = SE3BatchNorm(bnconv.Rs, affine=False)
        bn.train()

        conv = SE3Convolution(Rs_in, Rs_out, kernel_size)
        conv.train()
        conv.kernel = bnconv.kernel

        y2 = conv(bn(x))

        self.assertEqual(y2.size(1), n_out)

        # compare
        self.assertLess((y2 - y1).std() / y2.std(), 1e-4)

unittest.main()
