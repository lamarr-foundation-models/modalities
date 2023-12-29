from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Callable, List

import torch
import torch.nn as nn
from torch.distributed.fsdp import FullOptimStateDictConfig, FullStateDictConfig
from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
from torch.distributed.fsdp import StateDictType
from torch.optim import Optimizer

from llm_gym.checkpointing.checkpointing_instruction import CheckpointingInstruction
from llm_gym.exceptions import CheckpointingError


class CheckpointingEntityType(Enum):
    MODEL = "model"
    OPTIMIZER = "optimizer"


class CheckpointingExecutionIF(ABC):
    @abstractmethod
    def _save_checkpoint(self, model: FSDP, optimizer: Optimizer, global_train_sample_id: int):
        raise NotImplementedError

    @abstractmethod
    def _delete_checkpoint(self, global_train_sample_id: int):
        raise NotImplementedError

    @abstractmethod
    def load_model_checkpoint(self, model: nn.Module, experiment_id: str, global_train_sample_id: int) -> nn.Module:
        raise NotImplementedError

    @abstractmethod
    def load_optimizer_checkpoint(
        self, optimizer: Optimizer, model: nn.Module, experiment_id: str, global_train_sample_id: int
    ) -> Optimizer:
        raise NotImplementedError

    def run_checkpoint_instructions(
        self,
        checkpointing_instruction: CheckpointingInstruction,
        global_train_sample_id: int,
        model: FSDP,
        optimizer: Optimizer,
    ):
        if checkpointing_instruction.save_current:
            self._save_checkpoint(model=model, optimizer=optimizer, global_train_sample_id=global_train_sample_id)

        for global_train_sample_id in checkpointing_instruction.checkpoints_to_delete:
            self._delete_checkpoint(global_train_sample_id=global_train_sample_id)


class FSDPToDiscCheckpointing(CheckpointingExecutionIF):
    CHECKPOINT_STRUCTURE = "eid_<experiment_id>-<entity>-num_samples_<num_samples>.bin"

    def __init__(
        self,
        checkpoint_path: Path,
        experiment_id: str,
        global_rank: int,
        checkpointing_rank: int,
        model_wrapping_fn: Callable[[nn.Module, bool], FSDP],
    ):
        """Implementation of checkpointing to disc via FSDP

        Args:
            checkpoint_path (Path): folder path to the checkpoint
            experiment_id (str): ID of the experiment
            global_rank (int): global rank within the current process group
            checkpointing_rank (int): global rank that performs the checkpointing
            model_wrapping_fn (Callable[[nn.Module, bool], FSDP]): Wrapping function that wraps raw model.
                                                                   For FSDP, we pass in FSDPRunningEnv.wrap_model
        """
        self.checkpoint_path = checkpoint_path
        self.global_rank = global_rank
        self.checkpointing_rank = checkpointing_rank
        self.model_wrapping_fn = model_wrapping_fn
        self.experiment_id = experiment_id

    def _get_checkpointing_path(
        self,
        experiment_id: str,
        global_train_sample_id: int,
        entity_type: CheckpointingEntityType,
    ) -> Path:
        entity_file_name = (
            self.CHECKPOINT_STRUCTURE.replace("<experiment_id>", experiment_id)
            .replace("<entity>", entity_type.value)
            .replace("<num_samples>", str(global_train_sample_id + 1))
        )

        full_path = Path(self.checkpoint_path, experiment_id, entity_file_name)
        return full_path

    def _save_checkpoint(self, model: FSDP, optimizer: Optimizer, global_train_sample_id: int):
        # saving the model via FULL_STATE_DICT and checkpoint via FULL_OPTIM_STATE_DICT
        # TODO Need to check if LR schedulers also need checkpointing
        model_save_policy = FullStateDictConfig(offload_to_cpu=True, rank0_only=True)
        optim_save_policy = FullOptimStateDictConfig(offload_to_cpu=True, rank0_only=True)
        with FSDP.state_dict_type(
            module=model,
            state_dict_type=StateDictType.FULL_STATE_DICT,
            state_dict_config=model_save_policy,
            optim_state_dict_config=optim_save_policy,
        ):
            model_state = model.state_dict()
            optimizer_state = optimizer.state_dict()  # this gets the optimizer state dict object for each rank
            optim_state_dict = FSDP.optim_state_dict(
                model=model, optim=optimizer, optim_state_dict=optimizer_state
            )  # all the state dicts of the different ranks are synchronized

        if self.checkpointing_rank == self.global_rank:
            # save model
            model_checkpoint_path = self._get_checkpointing_path(
                experiment_id=self.experiment_id,
                global_train_sample_id=global_train_sample_id,
                entity_type=CheckpointingEntityType.MODEL,
            )
            model_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model_state, model_checkpoint_path)

            # save optimizer
            optimize_checkpoint_path = self._get_checkpointing_path(
                experiment_id=self.experiment_id,
                global_train_sample_id=global_train_sample_id,
                entity_type=CheckpointingEntityType.OPTIMIZER,
            )
            torch.save(optim_state_dict, optimize_checkpoint_path)

    def _get_paths_to_delete(self, global_train_sample_id: int) -> List[Path]:
        return [
            self._get_checkpointing_path(
                experiment_id=self.experiment_id, entity_type=entity_type, global_train_sample_id=global_train_sample_id
            )
            for entity_type in CheckpointingEntityType
        ]

    def _delete_checkpoint(self, global_train_sample_id: int):
        if self.global_rank != 0:
            return

        files_paths_to_delete = self._get_paths_to_delete(global_train_sample_id=global_train_sample_id)
        for full_path in files_paths_to_delete:
            if full_path.exists():
                # unlink removes the file
                full_path.unlink()
            else:
                raise CheckpointingError(f"Checkpoint {full_path} could not be removed. It does not exist!")

    def load_model_checkpoint(self, model: nn.Module, file_path: Path) -> nn.Module:
        # Loads the checkpoint as full state dicts into the model and optimizer on rank 0.
        # NOTE: The model and optimizer need to be sharded after calling this function!

        # model_save_policy = FullStateDictConfig(offload_to_cpu=True, rank0_only=True)
        # optim_save_policy = FullOptimStateDictConfig(offload_to_cpu=True, rank0_only=True)
        # with FSDP.state_dict_type(
        #     module=model,
        #     state_dict_type=StateDictType.FULL_STATE_DICT,
        #     state_dict_config=model_save_policy,
        #     optim_state_dict_config=optim_save_policy,
        # ):
        # we only load the model and optimizer on a single rank. The calling function must then
        # distribute the optimizer state and model parmeters to the other ranks.

        # load model
        if self.global_rank == self.checkpointing_rank:
            # load model on rank 0 into CPU RAM
            model_state = torch.load(file_path)
            model.load_state_dict(model_state)
        fsdp_model = self.model_wrapping_fn(model=model, sync_module_states=True)
        return fsdp_model

    def load_optimizer_checkpoint(self, optimizer: Optimizer, model: FSDP, file_path: Path) -> Optimizer:
        # load optimizer
        full_optimizer_state_dict = None
        if self.global_rank == self.checkpointing_rank:
            # load full optimizer state dict to rank 0 (CPU RAM)
            full_optimizer_state_dict = torch.load(file_path)

        # distribute the optimizer state dict from rank 0 to all the other ranks
        sharded_optimizer_state_dict = FSDP.scatter_full_optim_state_dict(
            full_optim_state_dict=full_optimizer_state_dict, model=model, group=None
        )
        optimizer.load_state_dict(sharded_optimizer_state_dict)

        return optimizer
