"""Dev server entry point.

psycopg's async mode requires a SelectorEventLoop, but uvicorn >= 0.36
hard-codes ProactorEventLoop as its Windows loop factory
(uvicorn.loops.asyncio.asyncio_loop_factory). We patch that factory before
starting the server, so the backend runs on a Selector loop on Windows.

Run the backend with:
    python run.py
"""
import asyncio
import sys

import uvicorn.loops.asyncio as _uvicorn_asyncio_loops

if sys.platform == "win32":
    # uvicorn imports this factory *by string path* at server start, so a
    # module-attribute patch is picked up (a local variable would not be).
    _uvicorn_asyncio_loops.asyncio_loop_factory = (
        lambda use_subprocess: asyncio.SelectorEventLoop
    )

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
