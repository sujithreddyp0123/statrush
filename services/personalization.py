"""
Personalization layer — adjusts edge/probability based on user history.
Stub implementation; expand with user preference data as needed.
"""
import logging

log = logging.getLogger("statrush.personalization")


def apply_personalization(result: dict, user: dict | None) -> dict:
    """
    Takes an inference result dict and optional auth user payload.
    Returns the result unchanged in this baseline implementation.
    """
    if not user:
        return result
    # Future: adjust edge weighting based on user's historical preferences
    return result
