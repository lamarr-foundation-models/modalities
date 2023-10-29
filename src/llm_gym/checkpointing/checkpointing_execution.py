from llm_gym.checkpointing.checkpointing import CheckpointingExecutionIF, CheckpointingInstruction
from llm_gym.exceptions import CheckpointingError
from torch.distributed.fsdp import FullyShardedDataParallel as FSDP, FullStateDictConfig, StateDictType
import torch
import os


class FSDPToDiscCheckpointing(CheckpointingExecutionIF):

    def __init__(self, checkpoint_path: str, experiment_id: str):
        self.checkpoint_path = checkpoint_path
        self.checkpoint_structure = f"{experiment_id}-<enitity>-<epoch>.bin"

    def run_checkpoint_instructions(self, checkpointing_instruction: CheckpointingInstruction, current_epoch: int, model: FSDP):
        if checkpointing_instruction.save_current:
            self._save_checkpoint(model=model, current_epoch=current_epoch)
        else:
            for epoch in checkpointing_instruction.checkpoints_to_delete:
                self._delete_checkpoint(epoch=epoch)

    def _save_checkpoint(self, model: FSDP, current_epoch: str):
        # TODO add optimizer checkpointing
        # https://pytorch.org/docs/stable/fsdp.html#torch.distributed.fsdp.FullyShardedDataParallel.optim_state_dict
        # Need to check if LR schedulers also need checkpointing
        save_policy = FullStateDictConfig(offload_to_cpu=True, rank0_only=True)
        with FSDP.state_dict_type(model, StateDictType.FULL_STATE_DICT, save_policy):
            cpu_state = model.state_dict()
        entity_file_name = self.checkpoint_structure.replace("<enitity>", "model").replace("<epoch>", current_epoch)
        full_path = os.path.join(self.checkpoint_path, entity_file_name)
        torch.save(cpu_state, full_path)

    def _delete_checkpoint(self, epoch: int):
        # TODO we need more logic to also delete optimizers and lr schedulers
        entity_file_name = self.checkpoint_structure.replace("<enitity>", "model").replace("<epoch>", epoch)
        full_path = os.path.join(self.checkpoint_path, entity_file_name)

        if os.path.exists(full_path):
            os.remove(full_path)
        else:
            raise CheckpointingError(f"Checkpoint {full_path} could not be removed. It does not exist!")