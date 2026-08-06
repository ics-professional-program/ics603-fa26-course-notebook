# The uv Dockerfile pattern from session 10.0.
#
# The uv tag is a complete version, so it keeps identifying the same image
# contents. `python:3.12-slim` names a series and can change. Record a digest
# when the image contents have to stay exact, and check both before the term.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

WORKDIR /app

# The dependency files are copied and installed BEFORE the application code, so
# that editing a line of Python does not invalidate the install layer. Reverse
# these two steps and every code edit reinstalls every package.
#
# uv.lock is committed. If you change a dependency in pyproject.toml, run
# `uv lock` and commit the result, or this build fails -- which is the intended
# behavior, because it reports that the lock file needs updating.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

EXPOSE 8000

# uv creates the virtual environment at /app/.venv, and `uv run` is what selects
# it. The bind address is 0.0.0.0, not 127.0.0.1: a server bound to 127.0.0.1
# inside a container accepts connections only from inside that same container,
# so a published port would forward requests to a server that refuses them.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
