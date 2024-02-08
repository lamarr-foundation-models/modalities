from pathlib import Path

import torch

from modalities.__main__ import Main, load_app_config_dict
from modalities.config.config import AppConfig
from modalities.models.coca.coca_model import AttentionalPooling, CoCa, CoCaConfig
from tests.conftest import _ROOT_DIR


def test_coca():
    # Create model
    config_file_path = _ROOT_DIR / Path("tests/models/coca/coca_config.yaml")
    config_dict = load_app_config_dict(config_file_path=config_file_path)
    coca_config = CoCaConfig.model_validate(config_dict)
    model = CoCa(**dict(coca_config))

    # Create dummy inputs
    dummy_input_image = torch.randn(1, 3, 224, 224)
    dummy_input_text = torch.randint(
        0, coca_config.text_decoder_config.vocab_size, (1, coca_config.multimodal_decoder_config.block_size)
    )
    dummy_input = dict(images=dummy_input_image, input_ids=dummy_input_text)

    # Create optimizer
    optimizer = torch.optim.SGD(model.parameters(), lr=0.001, momentum=0.9)

    # Run one training step
    optimizer.zero_grad()
    out = model(dummy_input)
    loss = out["logits"].sum()
    loss.backward()
    optimizer.step()

    # Test outputs
    assert "logits" in out
    assert "vision_cls" in out
    assert "text_cls" in out
    assert out["logits"].shape == (1, 1024, 50304)
    assert out["vision_cls"].shape == (1, 1, 768)
    assert out["text_cls"].shape == (1, 1, 768)


def test_attn_pool():
    model = AttentionalPooling(n_embd=768, n_head=8, bias=False, epsilon=1e-5)
    dummy_vision_embed = torch.randn(1, 256, 768)
    dummy_queries = torch.randn(1, 257, 768)
    out = model(dummy_vision_embed, dummy_queries)
    assert out.shape == (1, 257, 768)


def test_e2e_coca_training_run_without_checkpoint(monkeypatch):
    monkeypatch.setenv("RANK", "0")
    monkeypatch.setenv("LOCAL_RANK", "0")
    monkeypatch.setenv("WORLD_SIZE", "1")
    monkeypatch.setenv("MASTER_ADDR", "localhost")
    monkeypatch.setenv("MASTER_PORT", "9948")

    # Load config
    dummy_config_path = _ROOT_DIR / Path("config_files/config_example_coca.yaml")
    config_dict = load_app_config_dict(dummy_config_path)
    dummy_config = AppConfig.model_validate(config_dict)

    # Disable checkpointing
    dummy_config.checkpointing.checkpointing_strategy.config.k = 0

    main = Main(dummy_config)
    main.run()
