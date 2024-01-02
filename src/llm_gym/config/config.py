import json
import os
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Text

from pydantic import BaseModel, FilePath, PositiveFloat, PositiveInt, confloat, conint
from transformers import PretrainedConfig

from llm_gym.config.lookup_types import (
    CollatorTypes,
    DataloaderTypes,
    DatasetTypes,
    LossTypes,
    ModelTypes,
    OptimizerTypes,
    SamplerTypes,
    SchedulerTypes,
    TokenizerTypes,
)
from llm_gym.config.types import ProcessGroupBackendType
from llm_gym.fsdp.fsdp_running_env import RunningEnvConfig
from llm_gym.models.gpt2.gpt2_model import GPTConfig


class WandbConfig(BaseModel):
    project_name: str


class CudaKwargsConfig(BaseModel):
    num_workers: conint(ge=1)
    pin_memory: bool
    shuffle: bool


class TokenizerConfig(BaseModel):
    class GPT2TokenizerFastConfig(BaseModel):
        tokenizer_file: str  # FilePath not possible, since transformers.PretrainedTokenizers can only handle strings

    type_hint: TokenizerTypes
    config: GPT2TokenizerFastConfig


class DatasetConfig(BaseModel):
    class MemMapDatasetConfig(BaseModel):
        raw_data_path: FilePath
        index_path: Optional[FilePath] = None
        block_size: conint(gt=0)
        tokenizer: TokenizerConfig
        jq_pattern: str
        sample_key: str

    class PackedMemMapDatasetContinuousConfig(BaseModel):
        raw_data_path: Path
        block_size: conint(gt=0)
        sample_key: str

    class PackedMemMapDatasetMegatronConfig(BaseModel):
        raw_data_path: Path
        block_size: conint(gt=0)
        sample_key: str

    class MMapIndexedDatasetConfig(BaseModel):
        path: Path
        skip_warmup: bool

    type_hint: DatasetTypes
    config: MemMapDatasetConfig | PackedMemMapDatasetContinuousConfig | PackedMemMapDatasetMegatronConfig


class SamplerConfig(BaseModel):
    class DistributedSamplerConfig(BaseModel):
        rank: conint(ge=0)
        num_replicas: conint(ge=0)
        shuffle: bool

    type_hint: SamplerTypes
    config: DistributedSamplerConfig


class CollatorConfig(BaseModel):
    class GPT2LLMCollatorConfig(BaseModel):
        sample_key: str
        target_key: str

    type_hint: CollatorTypes
    config: GPT2LLMCollatorConfig


class DataLoaderConfig(BaseModel):
    class LLMDataLoaderConfig(CudaKwargsConfig):
        batch_size: conint(gt=0)
        dataloader_tag: str
        dataset: DatasetConfig
        sampler: SamplerConfig
        collate_fn: CollatorConfig

    type_hint: DataloaderTypes
    config: LLMDataLoaderConfig


class TrainingConfig(BaseModel):
    train_dataloader: DataLoaderConfig
    evaluation_dataloaders: Dict[Text, DataLoaderConfig]
    # TODO: use this in Progress Logging
    num_training_samples: conint(gt=0)
    callback_interval_in_samples: conint(gt=0)
    process_group_backend: ProcessGroupBackendType
    local_rank: conint(ge=0)
    global_rank: conint(ge=0)
    world_size: conint(ge=0)
    main_rank: conint(ge=0)

    @property
    def num_training_batches(self) -> int:
        exact = self.num_training_samples / self.train_dataloader.config.batch_size
        ret = self.num_training_samples // self.train_dataloader.config.batch_size
        if exact != ret:
            warnings.warn(f"Calculated num_training_batches is not an integer. Clipping {exact} to {ret} ")
        return ret

    @property
    def callback_interval_in_batches_per_rank(self):
        exact = self.callback_interval_in_samples / self.train_dataloader.config.batch_size / self.world_size
        ret = self.callback_interval_in_samples // self.train_dataloader.config.batch_size // self.world_size
        if exact != ret:
            warnings.warn(
                f"Calculated callback_interval_in_batches_per_rank is not an integer. Clipping {exact} to {ret} "
            )
        return ret

    @property
    def num_batches_per_rank(self):
        exact = self.num_training_batches / self.world_size
        ret = self.num_training_batches // self.world_size
        if exact != ret:
            warnings.warn(f"Calculated num_batches_per_rank is not an integer. Clipping {exact} to {ret} ")
        return ret


# TODO: remove this?? Seems unnecessary to add another composition layer here
class GPT2Config(BaseModel):
    config: GPTConfig


class ModelConfig(BaseModel):
    type_hint: ModelTypes
    config: GPT2Config


class CLMCrossEntropyLossConfig(BaseModel):
    target_key: str
    prediction_key: str


class LossConfig(BaseModel):
    type_hint: LossTypes
    config: CLMCrossEntropyLossConfig


class AdamWConfig(BaseModel):
    lr: confloat(ge=0.0)


class OptimizerConfig(BaseModel):
    type_hint: OptimizerTypes
    config: AdamWConfig


class OneCycleLRConfig(BaseModel):
    max_lr: PositiveFloat
    total_steps: conint(ge=1)
    pct_start: confloat(ge=0.0)
    anneal_strategy: str
    cycle_momentum: bool
    base_momentum: float | List
    max_momentum: float | List
    div_factor: PositiveFloat
    final_div_factor: PositiveFloat
    three_phase: bool
    last_epochs: int
    verbose: bool


class StepLRConfig(BaseModel):
    step_size: conint(ge=1)
    gamma: confloat(ge=0.0)


class ConstantLRConfig(BaseModel):
    factor: PositiveFloat
    total_iters: PositiveInt


class SchedulerConfig(BaseModel):
    type_hint: SchedulerTypes
    config: StepLRConfig | ConstantLRConfig | OneCycleLRConfig


class CheckpointConfig(BaseModel):
    checkpointing_rank: conint(ge=0, le=os.environ.get("WORLD_SIZE", 0))
    dir_path: Path


class AppConfig(BaseModel):
    training: TrainingConfig
    loss: LossConfig
    running_env: RunningEnvConfig
    model: ModelConfig
    optimizer: OptimizerConfig
    scheduler: SchedulerConfig
    checkpoint: CheckpointConfig
    wandb: WandbConfig


class PretrainedGPTConfig(PretrainedConfig):
    model_type = "llm_gym_gpt2"

    def __init__(self, config: GPTConfig = None, **kwargs):
        if type(config) == dict:
            config = GPTConfig(**config)
        self.config = config

        super().__init__(**kwargs)

    def to_json_string(self, use_diff: bool = True) -> str:
        if self.config:
            json_dict = {"config": self.config.__dict__.copy(), "model_type": self.model_type}
            json_dict["config"]["attention"] = {
                "attention_type": self.config.attention.attention_type.value,
                "scaling_factor": self.config.attention.scaling_factor,
            }
            json_dict["config"]["weight_init"] = {
                "mean": self.config.weight_init.mean,
                "std": self.config.weight_init.std,
            }
        else:
            json_dict = {}
        return json.dumps(json_dict)
