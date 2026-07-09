"""Memory stores: Translator (Policy), Story (Fact), Language (Pattern).

v0 persists policies as JSON behind a store interface; the backend can later switch to
SQLite (production) or a graph (future) without changing callers.
"""
