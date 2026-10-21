"""Small deterministic tensor interface fixture; no ML runtime in module CI."""

from __future__ import annotations

import math
import struct
from types import SimpleNamespace


class Tensor:
    dtype = "fixture_float32"
    device = "fixture_cpu"

    def __init__(self, values):
        self.values = list(values)

    def __setitem__(self, index, value):
        self.values[index] = value.item() if isinstance(value, Tensor) else value

    def __getitem__(self, index):
        if isinstance(index, Tensor):
            return Tensor(self.values[int(item)] for item in index.values)
        return Tensor([self.values[index]])

    def __add__(self, other):
        return Tensor(value + other for value in self.values)

    def __sub__(self, other):
        return Tensor(
            left - right for left, right in zip(self.values, other.values, strict=True)
        )

    def __lt__(self, other):
        return Tensor(value < other for value in self.values)

    def __pow__(self, other):
        return Tensor(value**other for value in self.values)

    def __isub__(self, other):
        self.values = [value - other for value in self.values]
        return self

    def item(self):
        return self.values[0]

    def all(self):
        return all(self.values)

    def clone(self):
        return Tensor(self.values)

    def float(self):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self

    def tobytes(self):
        return struct.pack(f"{len(self.values)}f", *self.values)

    def numel(self):
        return len(self.values)

    def element_size(self):
        return 4

    def data_ptr(self):
        return id(self.values)

    def zero_(self):
        self.values = [0 for _ in self.values]
        return self


class MiniTorch:
    __version__ = "fixture_not_an_inference_runtime"

    def __init__(self):
        self.cuda = SimpleNamespace(
            is_available=lambda: False,
            synchronize=lambda: None,
            reset_peak_memory_stats=lambda: None,
            max_memory_allocated=lambda: 0,
        )

    def zeros(self, *shape):
        return Tensor([0.0] * math.prod(shape))

    def manual_seed(self, seed):
        pass

    def set_num_threads(self, value):
        pass

    def isfinite(self, tensor):
        return Tensor(math.isfinite(value) for value in tensor.values)

    def argmax(self, tensor):
        return Tensor(
            [max(range(len(tensor.values)), key=lambda index: tensor.values[index])]
        )

    def softmax(self, tensor, *, dim):
        values = [math.exp(value - max(tensor.values)) for value in tensor.values]
        return Tensor(value / sum(values) for value in values)

    def sort(self, tensor, *, descending):
        indices = sorted(
            range(len(tensor.values)),
            key=lambda index: tensor.values[index],
            reverse=descending,
        )
        return Tensor(tensor.values[index] for index in indices), Tensor(indices)

    def cumsum(self, tensor, *, dim):
        total = 0
        values = []
        for value in tensor.values:
            total += value
            values.append(total)
        return Tensor(values)

    def where(self, condition, tensor, zero):
        return Tensor(
            value if keep else zero
            for value, keep in zip(tensor.values, condition.values, strict=True)
        )

    def multinomial(self, tensor, count):
        return self.argmax(tensor)
