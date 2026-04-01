from __future__ import annotations

import streamlit as st

from web_ui.models import PipelineResult


STATE_KEY = "web_ui_last_result"


def set_result_state(result: PipelineResult) -> None:
    """Persist the latest pipeline result in session state."""

    st.session_state[STATE_KEY] = result


def get_result_state() -> PipelineResult | None:
    """Return the latest pipeline result from session state."""

    result = st.session_state.get(STATE_KEY)
    if isinstance(result, PipelineResult):
        return result
    return None


def clear_result_state() -> None:
    """Clear the last pipeline result from session state."""

    st.session_state.pop(STATE_KEY, None)


def set_error_state(message: str) -> None:
    """Store a lightweight error result."""

    set_result_state(
        PipelineResult(
            stage="word2md",
            run_id="",
            input_file="",
            error_message=message,
        )
    )
