"""HTTP layer for the BigFlavor backend.

Per-concern FastAPI routers (admin, search, agent, radio, tools) plus the radio
playback/queue/listener logic in ``radio_service`` and the shared startup
singletons, dependencies, and request models in ``dependencies``. The routers
are mounted on the app created in ``backend_api.py``.
"""
