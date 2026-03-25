"""only_prompt_local_llm source package."""

from Contract_Review_System.common.local_llm_client import load_runtime_config

from .cli import main
from .local_model_runner import run_local_prediction

__all__ = ["load_runtime_config", "main", "run_local_prediction"]
