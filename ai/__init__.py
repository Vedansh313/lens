"""Isolated visual-search module: CLIP + FAISS retrieval and metadata re-ranking.

The search logic (search_system.py) and model artifacts (models/) live here,
independent of the web/API layer in backend/. The backend imports build_search
from this package; it does not reach into the search internals.
"""
