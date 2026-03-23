"""only_prompt_local_llm source package."""

from .cli import main
from .local_model_runner import load_runtime_config, run_local_prediction

__all__ = ["load_runtime_config", "main", "run_local_prediction"]
