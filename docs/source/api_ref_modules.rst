=================
torchtune.modules
=================

.. currentmodule:: torchtune.modules

Modeling Components and Building Blocks
---------------------------------------

.. autosummary::
    :toctree: generated/
    :nosignatures:

    CausalSelfAttention
    FeedForward
    KVCache
    get_cosine_schedule_with_warmup
    RotaryPositionalEmbeddings
    RMSNorm
    Fp32LayerNorm
    TransformerDecoderLayer
    TransformerDecoder
    VisionTransformer

Multimodal Modeling Components and Building Blocks
---------------------------------------

.. autosummary::
    :toctree: generated/
    :nosignatures:

    GroupedQueryAttention
    MMTransformerDecoder
    TransformerSelfAttentionLayer
    TransformerCrossAttentionLayer
    TanhGate

Tokenizers
------------------------

.. autosummary::
    :toctree: generated/
    :nosignatures:

    tokenizers.SentencePieceTokenizer
    tokenizers.TikTokenTokenizer
    tokenizers.Tokenizer

PEFT Components
---------------

.. autosummary::
    :toctree: generated/
    :nosignatures:

    peft.LoRALinear
    peft.AdapterModule
    peft.get_adapter_params
    peft.set_trainable_params
    peft.validate_missing_and_unexpected_for_lora
    peft.validate_state_dict_for_lora
    peft.disable_adapter

Module Utilities
------------------
These are utilities that are common to and can be used by all modules.

.. autosummary::
   :toctree: generated/
   :nosignatures:

   common_utils.reparametrize_as_dtype_state_dict_post_hook

Loss
------------------

.. autosummary::
   :toctree: generated/
   :nosignatures:

   loss.DPOLoss

Vision Transforms
------------------
Functions used for preprocessing images.

.. autosummary::
   :toctree: generated/
   :nosignatures:

    transforms.get_canvas_best_fit
    transforms.resize_with_pad
    transforms.tile_crop
    transforms.find_supported_resolutions
    transforms.VisionCrossAttentionMask
