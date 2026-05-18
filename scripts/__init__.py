"""Top-level scripts package.

Allows ``scripts.run_demo`` to be imported from tests; the existing
``scripts/seed_random.py`` and ``scripts/check_db.py`` are launched as
``uv run python scripts/<name>.py`` so they did not previously need a
package marker.
"""
