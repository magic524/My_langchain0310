"""only_prompt_local_llm source package."""

from Contract_Review_System.common.local_llm_client import load_runtime_config

from .cli import main
from .local_model_runner import run_local_prediction
from .word_comment_export import export_local_llm_comment_docs

__all__ = [
    "export_local_llm_comment_docs",
    "load_runtime_config",
    "main",
    "run_local_prediction",
]
