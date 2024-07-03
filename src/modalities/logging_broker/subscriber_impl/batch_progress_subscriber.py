from typing import Dict, Tuple

from rich.console import Group
from rich.live import Live
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn
from rich.rule import Rule
from rich.text import Text

from modalities.logging_broker.messages import BatchProgressUpdate, ExperimentStatus, Message
from modalities.logging_broker.subscriber import MessageSubscriberIF


class DummyProgressSubscriber(MessageSubscriberIF[BatchProgressUpdate]):
    def consume_message(self, message: Message[BatchProgressUpdate]):
        pass

    def consume_key_value(self, key: str, value: str):
        pass

class RichProgressSubscriber(MessageSubscriberIF[BatchProgressUpdate]):
    """A subscriber object for the RichProgress observable."""

    _live_display: Live = None

    def __init__(
        self,
        train_split_num_steps: Dict[str, Tuple[int, int]],
        eval_splits_num_steps: Dict[str, int],
    ) -> None:
        # train split progress bar
        self.train_splits_progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
        )
        self.train_split_task_ids = {}
        for split_key, (split_dataloader_num_steps, completed_steps) in train_split_num_steps.items():
            task_id = self.train_splits_progress.add_task(
                description=split_key, completed=completed_steps, total=split_dataloader_num_steps
            )
            self.train_split_task_ids[split_key] = task_id

        # eval split progress bars
        self.eval_splits_progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
        )
        self.eval_split_task_ids = {}
        for split_key, split_dataloader_num_steps in eval_splits_num_steps.items():
            task_id = self.eval_splits_progress.add_task(description=split_key, total=split_dataloader_num_steps)
            self.eval_split_task_ids[split_key] = task_id

        group = Group(
            Text(text="\n\n\n"),
            Rule(style="#AAAAAA"),
            Text(text="Training", style="blue"),
            self.train_splits_progress,
            Rule(style="#AAAAAA"),
            Text(text="Evaluation", style="blue"),
            self.eval_splits_progress,
        )

        live = Live(group)
        self.register_live_display(live_display=live)
        live.start()

    @classmethod
    def register_live_display(cls, live_display: Live):
        """
        Only one instance of rich.live.Live can run at the same time.
        Therefore we use a singleton approach to have only one active,
         by storing the active reference as class-field here.
        """
        if cls._live_display is not None:
            cls._live_display.stop()
        cls._live_display = live_display

    def consume_message(self, message: Message[BatchProgressUpdate]):
        """Consumes a message from a message broker."""
        batch_progress = message.payload

        if batch_progress.experiment_status == ExperimentStatus.TRAIN:
            task_id = self.train_split_task_ids[batch_progress.dataloader_tag]
            self.train_splits_progress.update(
                task_id=task_id,
                completed=batch_progress.step_id + 1,
            )
        else:
            task_id = self.eval_split_task_ids[batch_progress.dataloader_tag]
            self.eval_splits_progress.update(
                task_id=task_id,
                completed=batch_progress.step_id + 1,
            )
