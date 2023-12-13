import os
from unittest.mock import call

import torch

from llm_gym.batch import DatasetBatch
from llm_gym.evaluator import Evaluator
from tests.conftest import set_env_cpu


def test_evaluate_cpu(
    monkeypatch,
    nn_model_mock,
    loss_mock,
    llm_data_loader_mock,
    progress_publisher_mock,
):
    # TODO: does not really ensure cpu-only usage. Alternative could be to patch `torch.cuda.is_available() = False`
    set_env_cpu(monkeypatch=monkeypatch)

    batch_size = 32
    seq_len = 64
    num_batches = 4
    sample_key = "input_ids"
    target_key = "target_ids"

    sample_tensor = torch.randint(size=(batch_size, seq_len), low=1, high=100)
    samples = {sample_key: sample_tensor[:, :-1]}
    targets = {target_key: sample_tensor[:, 1:]}

    batches = [DatasetBatch(targets=targets, samples=samples) for _ in range(num_batches)]

    llm_data_loader_mock.__iter__ = lambda _: iter(batches)

    evaluator = Evaluator(
        local_rank=int(os.getenv("LOCAL_RANK")),
        batch_progress_publisher=progress_publisher_mock,
        evaluation_result_publisher=progress_publisher_mock,
    )

    evaluator.evaluate(model=nn_model_mock, data_loaders=[llm_data_loader_mock], loss_fun=loss_mock, train_batch_id=0)
    nn_model_mock.forward.assert_has_calls([call(b.samples) for b in batches])
