"""Shared pytest fixtures.

Note: this file used to carry an autouse fixture clearing the
``get_settings`` cache between tests. The cache was removed (settings
construction is cheap; a cache silently ignored later env changes), so the
fixture went with it — do not re-add it without re-adding the cache.
"""
