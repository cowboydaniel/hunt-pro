# Containerized Development

This guide provides a repeatable Docker workflow for developing Hunt Pro without
managing the Python and Qt dependencies on the host machine. The container image
mirrors the tooling that runs in continuous integration and includes every
required package for linting and running the automated tests.

## Prerequisites

- [Docker](https://docs.docker.com/engine/install/) 20.10 or newer
- At least 4 GB of disk space available for the image and Python cache layers

## Build the image

From the repository root run:

```bash
docker build -f Dockerfile.dev -t hunt-pro-dev .
```

The build installs runtime dependencies from `requirements.txt` plus the
additional tooling defined in `requirements-dev.txt`.

## Start a development shell

Launch an interactive shell with the local repository mounted into the
container so that edits made in the container are written back to the host:

```bash
docker run --rm -it \
  -v "$(pwd)":/workspace \
  -w /workspace \
  hunt-pro-dev bash
```

The container automatically drops privileges to a non-root user that matches the
UID and GID passed during `docker build` (defaults to 1000). When the container
starts you can run the usual development workflow:

```bash
make lint
pytest
python -m hunt_pro
```

## Graphical sessions

Qt-based user interfaces require an available display server. When running on
Linux you can forward your X11 display by adding the following flags:

```bash
xhost +local:
docker run --rm -it \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$(pwd)":/workspace \
  -w /workspace \
  hunt-pro-dev python -m hunt_pro
```

For macOS or Windows hosts consider using [XQuartz](https://www.xquartz.org/)
(macOS) or an X server such as [VcXsrv](https://sourceforge.net/projects/vcxsrv/)
(Windows) to expose a display before launching the container.
