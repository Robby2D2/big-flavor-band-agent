"""HTTP layer for the BigFlavor backend.

Per-concern FastAPI routers (search, agent, radio, admin, tools) and the
RadioService that holds radio playback/queue state. The routers are mounted
on the app created in `backend_api.py`.
"""
