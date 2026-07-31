# Development-machine setup

The project uses a user-space Blender installation so that a development
machine does not need root access.

```bash
BLENDER_ROOT=/path/to/tools scripts/bootstrap_linux.sh
```

The official Blender binary dynamically loads `libEGL.so.1` even in background
mode. If the host does not provide it, create a dedicated Conda environment
instead of borrowing libraries from another project:

```bash
conda create -p /path/to/env \
  python=3.11 nodejs=22 libegl=1.7 libgl=1.7 libglvnd=1.7
```

Some containerized NVIDIA machines mount the driver libraries and devices but
omit the GLVND vendor manifest. Keep a private manifest outside the repository:

```json
{
  "file_format_version": "1.0.0",
  "ICD": {
    "library_path": "/usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.0"
  }
}
```

Configure the repository through the ignored `.env.local` file:

```bash
export SMCB_PYTHON=/path/to/env/bin/python
export BLENDER_BIN=/path/to/tools/blender/blender
export PATH=/path/to/env/bin:$PATH
export LD_LIBRARY_PATH=/path/to/env/lib
export __EGL_VENDOR_LIBRARY_FILENAMES=/path/to/10_nvidia.json
```

Then verify both dependencies and a real 64x64 background render:

```bash
source .env.local
make doctor
make smoke
```

Keep proxy settings and machine-specific paths outside Git. Services must bind
to `127.0.0.1`; remote access should use an authenticated tunnel.
