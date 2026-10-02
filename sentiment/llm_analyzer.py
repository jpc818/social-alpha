"""Compatibility wrapper — prefer src.sentiment for new code."""

from src.sentiment import analyze_dataset, analyze_text

__all__ = ["analyze_text", "analyze_dataset"]
