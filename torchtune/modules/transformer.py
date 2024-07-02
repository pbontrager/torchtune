# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
import copy
from abc import abstractmethod
from typing import Optional, Protocol, runtime_checkable

import torch
from torch import nn, Tensor

from torchtune.modules import GroupedQueryAttention, KVCache


@runtime_checkable
class TransformerLayer(Protocol):
    """Transformer layer meant to by used in TransformerDecoder"""

    @abstractmethod
    def forward(
        self,
        x: Tensor,
        *,
        mask: Optional[Tensor] = None,
        encoder_input: Optional[Tensor] = None,
        encoder_mask: Optional[Tensor] = None,
        input_pos: Optional[Tensor] = None,
    ) -> Tensor:
        """
        Args:
            x (Tensor): input sequence tensor
            mask (Optional[Tensor]): boolean tensor which contains the attention mask
            encoder_input (Optional[Tensor]): secondary input sequence tensor
                transformer layers. This input is ignored and does nothing in self attention.
            encoder_mask (Optional[Tensor]):  boolearn tensor to mask connections between x and encoder_input
            input_pos (Optional[Tensor]): Optional tensor which contains the position ids of each token.

        Returns:
            Tensor: output tensor with same shape as input
        """


class TransformerSelfAttentionLayer(nn.Module):
    """Transformer layer derived from the Llama2 model. Normalization is applied before the attention **and** FF layer.

    Args:
        attn (GroupedQueryAttention): Attention module.
        mlp (nn.Module): Feed-forward module.
        attn_norm (Optinoal[nn.Module]): Normalization to be applied before self-attention.
        mlp_norm (Optional[nn.Module]): Normalization to be applied before the feed-forward layer.
        attn_scale (Optinoal[nn.Module]): Module to scale self-attention output.
        mlp_scale (Optional[nn.Module]): Module to scale the feed-forward output.
    """

    def __init__(
        self,
        attn: GroupedQueryAttention,
        mlp: nn.Module,
        *,
        attn_norm: Optional[nn.Module] = None,
        mlp_norm: Optional[nn.Module] = None,
        attn_scale: Optional[nn.Module] = None,
        mlp_scale: Optional[nn.Module] = None,
    ) -> None:
        super().__init__()
        self.attn = attn
        self.mlp = mlp
        self.attn_norm = attn_norm or nn.Identity()
        self.mlp_norm = mlp_norm or nn.Identity()
        self.attn_scale = attn_scale or nn.Identity()
        self.mlp_scale = mlp_scale or nn.Identity()

    def forward(
        self,
        x: Tensor,
        *,
        mask: Optional[Tensor] = None,
        encoder_input: Optional[Tensor] = None,
        encoder_mask: Optional[Tensor] = None,
        input_pos: Optional[Tensor] = None,
    ) -> Tensor:
        """
        Args:
            x (Tensor): input tensor with shape
                [batch_size x seq_length x embed_dim]
            mask (Optional[Tensor]): Optional boolean tensor which contains the attention mask
                with shape [batch_size x seq_length x seq_length]. This is applied after
                the query-key multiplication and before the softmax. A value of True in row i
                and column j means token i attends to token j. A value of False means token i
                does not attend to token j. If no mask is specified, a causal mask
                is used by default. Default is None.
            encoder_input (Optional[Tensor]): input to keep a consistent signature accross
                transformer layers. This input is ignored and does nothing in self attention.
            encoder_mask (Optional[Tensor]):  input to keep a consistent signature accross
                transformer layers. This input is ignored and does nothing in self attention.
            input_pos (Optional[Tensor]): Optional tensor which contains the position ids
                of each token. During training, this is used to indicate the positions
                of each token relative to its sample when packed, shape [b x s].
                During inference, this indicates the position of the current token.
                If none, assume the index of the token is its position id. Default is None.

        Returns:
            Tensor: output tensor with same shape as input
                [batch_size x seq_length x embed_dim]
        """
        # Input tensor and attention output have the same shape
        # [b, s, d]
        # Norm applied before self-attention
        attn_out = self.attn(self.attn_norm(x), mask=mask, input_pos=input_pos)

        # Residual connection; shape: [batch_size, seq_length, embed_dim]
        h = self.attn_scale(attn_out) + x

        # Norm applied before the feedforward layer
        mlp_out = self.mlp(self.mlp_norm(h))

        # Residual connection; shape: [batch_size, seq_length, embed_dim]
        out = h + self.mlp_scale(mlp_out)
        return out


class TransformerCrossAttentionLayer(nn.Module):
    """Cross attention Transformer layer derived from the Llama2 model self attention layer.
       Normalization is applied before the attention **and** FF layer.

    Args:
        attn (GroupedQueryAttention): Attention module.
        mlp (nn.Module): Feed-forward module.
        attn_norm (Optinoal[nn.Module]): Normalization to be applied before self-attention.
        mlp_norm (Optional[nn.Module]): Normalization to be applied before the feed-forward layer.
        attn_scale (Optinoal[nn.Module]): Module to scale self-attention output.
        mlp_scale (Optional[nn.Module]): Module to scale the feed-forward output.
    """

    def __init__(
        self,
        attn: GroupedQueryAttention,
        mlp: nn.Module,
        *,
        attn_norm: Optional[nn.Module] = None,
        mlp_norm: Optional[nn.Module] = None,
        attn_scale: Optional[nn.Module] = None,
        mlp_scale: Optional[nn.Module] = None,
    ) -> None:
        super().__init__()
        assert (
            attn.pos_embeddings is None
        ), "Positions are not computed for encoder inputs"
        self.attn = attn
        self.mlp = mlp
        self.attn_norm = attn_norm or nn.Identity()
        self.mlp_norm = mlp_norm or nn.Identity()
        self.attn_scale = attn_scale or nn.Identity()
        self.mlp_scale = mlp_scale or nn.Identity()

    def output_mask(self, mask: Optional[Tensor]) -> Optional[Tensor]:
        if mask is None:
            return None
        if mask.dtype == torch.bool:
            mask = ~mask
        else:
            mask = torch.isneginf(mask)
        mask = torch.all(mask, dim=-1, keepdim=True)
        return mask

    def forward(
        self,
        x: Tensor,
        *,
        mask: Optional[Tensor] = None,
        encoder_input: Optional[Tensor] = None,
        encoder_mask: Optional[Tensor] = None,
        input_pos: Optional[Tensor] = None,
    ) -> Tensor:
        """
        Args:
            x (Tensor): input tensor with shape
                [batch_size x seq_length x embed_dim]
            mask (Optional[Tensor]): Optional boolean tensor which contains the attention mask
                with shape [batch_size x seq_length x seq_length]. This is applied after
                the query-key multiplication and before the softmax. A value of True in row i
                and column j means token i attends to token j. A value of False means token i
                does not attend to token j. If no mask is specified, a causal mask
                is used by default. Default is None.
            encoder_input (Optional[Tensor]): Optional second input to cross attend with x. Shape
                [batch_size x seq_length x embed_dim] (seq_length and embed_dim may very from x)
            encoder_mask (Optional[Tensor]):  Cross attention boolean tensor with shape
                [batch_size x x_seq_len x encoder_seq_len]
            input_pos (Optional[Tensor]): Optional tensor which contains the position ids
                of each token. During training, this is used to indicate the positions
                of each token relative to its sample when packed, shape [b x s].
                During inference, this indicates the position of the current token.
                If none, assume the index of the token is its position id. Default is None.

        Returns:
            Tensor: output tensor with same shape as input
                [batch_size x seq_length x embed_dim]
        """
        # Skip cross attention when no secondary input
        if encoder_input is None:
            return x

        # A mask of tokens (x) with no encoder_input
        output_mask = self.output_mask(encoder_mask)

        # Input tensor and attention output have the same shape
        # [b, s, d]
        # Norm applied before self-attention
        attn_out = self.attn(
            self.attn_norm(x), encoder_input, mask=encoder_mask, input_pos=input_pos
        )
        if output_mask is not None:
            attn_out.masked_fill_(output_mask, 0)

        # Residual connection; shape: [batch_size, seq_length, embed_dim]
        h = self.attn_scale(attn_out) + x

        # Norm applied before the feedforward layer
        mlp_out = self.mlp(self.mlp_norm(h))
        if output_mask is not None:
            mlp_out.masked_fill_(output_mask, 0)

        # Residual connection; shape: [batch_size, seq_length, embed_dim]
        out = h + self.mlp_scale(mlp_out)
        return out


def _get_clones(module: nn.Module, n: int) -> nn.ModuleList:
    """
    Return a list of ``n`` identical layers.

    Args:
        module (nn.Module): module to be cloned
        n (int): number of clones

    Returns:
        nn.ModuleList: list of ``n`` identical layers
    """
    # FIXME: copy.deepcopy() is not defined on nn.module
    return nn.ModuleList([copy.deepcopy(module) for i in range(n)])


class TransformerDecoder(nn.Module):
    """
    Transformer Decoder derived from the Llama2 architecture.

    Args:
        tok_embeddings (nn.Embedding): PyTorch embedding layer, to be used to move
            tokens to an embedding space.
        layer (TransformerDecoderLayer): Transformer Decoder layer.
        num_layers (int): Number of Transformer Decoder layers.
        max_seq_len (int): maximum sequence length the model will be run with, as used
            by :func:`~torchtune.modules.KVCache`
        num_heads (int): number of query heads. For MHA this is also the
            number of heads for key and value. This is used to setup the
            :func:`~torchtune.modules.KVCache`
        head_dim (int): embedding dimension for each head in self-attention. This is used
            to setup the :func:`~torchtune.modules.KVCache`
        norm (nn.Module): Callable that applies normalization to the output of the decoder,
            before final MLP.
        output (nn.Linear): Callable that applies a linear transformation to the output of
            the decoder.

    Note:
        Arg values are checked for correctness (eg: ``attn_dropout`` belongs to [0,1])
        in the module where they are used. This helps reduces the number of raise
        statements in code and improves readability.
    """

    def __init__(
        self,
        tok_embeddings: nn.Embedding,
        layer: TransformerLayer,
        num_layers: int,
        max_seq_len: int,
        num_heads: int,
        head_dim: int,
        norm: nn.Module,
        output: nn.Linear,
    ) -> None:
        super().__init__()

        self.tok_embeddings = tok_embeddings
        self.layers = _get_clones(layer, num_layers)
        self.norm = norm
        self.output = output
        self.max_seq_len = max_seq_len
        self.num_heads = num_heads
        self.head_dim = head_dim
        self.causal_mask = None

    def setup_caches(self, batch_size: int, dtype: torch.dtype) -> None:
        """Setup key value caches for attention calculation.

        Args:
            batch_size (int): batch size for the caches.
            dtype (torch.dtype): dtype for the caches.
        """
        for layer in self.layers:
            layer.attn.kv_cache = KVCache(
                batch_size=batch_size,
                max_seq_len=self.max_seq_len,
                num_heads=self.num_heads,
                head_dim=self.head_dim,
                dtype=dtype,
            )

        # causal_mask is used during inference to ensure we're attending
        # to the right tokens
        self.causal_mask = torch.tril(
            torch.ones(self.max_seq_len, self.max_seq_len, dtype=torch.bool)
        )

    def reset_caches(self):
        """Reset the key value caches."""
        if self.layers[0].attn.kv_cache is None:
            raise RuntimeError(
                "Key value caches are not setup. Call ``setup_caches()`` first."
            )

        for layer in self.layers:
            layer.attn.kv_cache.reset()

    def forward(
        self,
        tokens: Tensor,
        *,
        mask: Optional[Tensor] = None,
        encoder_input: Optional[Tensor] = None,
        encoder_mask: Optional[Tensor] = None,
        input_pos: Optional[Tensor] = None,
    ) -> Tensor:
        """
        Args:
            tokens (Tensor): input tensor with shape [b x s]
            mask (Optional[Tensor]): Optional boolean tensor which contains the attention mask
                with shape [b x s x s]. This is applied after the query-key multiplication and
                before the softmax. A value of True in row i and column j means token i attends
                to token j. A value of False means token i does not attend to token j. If no
                mask is specified, a causal mask is used by default. Default is None.
            encoder_input (Optional[Tensor]): Optional second input to cross attend with x. Shape
                [batch_size x seq_length x embed_dim] (seq_length and embed_dim may very from x)
            encoder_mask (Optional[Tensor]):  Cross attention boolean tensor with shape
                [batch_size x x_seq_len x encoder_seq_len]
            input_pos (Optional[Tensor]): Optional tensor which contains the position ids
                of each token. During training, this is used to indicate the positions
                of each token relative to its sample when packed, shape [b x s].
                During inference, this indicates the position of the current token.
                If none, assume the index of the token is its position id. Default is None.

        Note: At the very first step of inference, when the model is provided with a prompt,
        ``input_pos`` would contain the positions of all of the tokens in the prompt
        (eg: ``torch.arange(prompt_length)``). This is because we will need to compute the
        KV values for each position.

        Returns:
            Tensor: output tensor with shape [b x s x v]

        Raises:
            ValueError: if causal_mask is set but input_pos is None
            ValueError: if seq_len of x is bigger than max_seq_len

        Notation used for tensor shapes:
            - b: batch size
            - s: sequence length
            - v: vocab size
            - d: embed dim
            - m_s: max seq len
        """
        # input tensor of shape [b, s]
        bsz, seq_len = tokens.shape

        if seq_len > self.max_seq_len:
            raise ValueError(
                f"seq_len ({seq_len}) of input tensor should be smaller "
                f"than max_seq_len ({self.max_seq_len})"
            )

        # shape: [b, s, d]
        h = self.tok_embeddings(tokens)

        if self.causal_mask is not None:
            if input_pos is None:
                raise ValueError(
                    "Caches are setup, but the position of input token is missing"
                )
            if mask is not None:
                raise ValueError(
                    "An attention mask was set. Cannot use a non-causal mask for inference"
                )
            # shape: [1, input_pos_len, m_s]
            # in most cases input_pos_len should be 1
            mask = self.causal_mask[None, input_pos]

        for layer in self.layers:
            # shape: [b, s, d]
            h = layer(
                h,
                mask=mask,
                encoder_input=encoder_input,
                encoder_mask=encoder_mask,
                input_pos=input_pos,
            )

        # shape: [b, s, d]
        h = self.norm(h)

        # shape: [b, s, out_dim] - out_dim is usually the vocab size
        output = self.output(h).float()
        return output
