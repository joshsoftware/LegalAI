"""
kb/ — knowledge-base (RAG) layer.

  loader.py    — reads the JSONL file into a list of dicts
  retriever.py — substring-matches source text, formats the terminology block
"""

from .loader import load_kb
from .retriever import retrieve, format_terminology_block

__all__ = ["load_kb", "retrieve", "format_terminology_block"]
