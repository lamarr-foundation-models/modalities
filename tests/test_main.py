import pytest
import torch.cuda

from llm_gym.__main__ import Main


def no_gpu_available() -> bool:
    return not torch.cuda.is_available()


@pytest.mark.skipif(
    no_gpu_available(), reason="This e2e test verifies a GPU-Setup and uses components, which do not support CPU-only."
)
def test_e2e_training_run_wout_ckpt(monkeypatch, indexed_dummy_data_path, dummy_config):
    # patch in env variables
    monkeypatch.setenv("MASTER_ADDR", "localhost")
    monkeypatch.setenv("MASTER_PORT", "9948")

    dummy_config.training.train_dataloader.config.dataset.config.raw_data_path = indexed_dummy_data_path.raw_data_path
    for val_dataloader_config in dummy_config.training.evaluation_dataloaders.values():
        val_dataloader_config.config.dataset.config.raw_data_path = indexed_dummy_data_path.raw_data_path
    main = Main(dummy_config)
    main.run()