# Development-machine setup

The project uses a user-space Blender installation so that a development
machine does not need root access.

```bash
BLENDER_ROOT=/path/to/tools scripts/bootstrap_linux.sh
printf 'export BLENDER_BIN=%s\n' /path/to/tools/blender/blender > .env.local
printf 'export PATH=%s:$PATH\n' /path/to/tools/blender >> .env.local
source .env.local
make doctor
```

Keep proxy settings and machine-specific paths outside Git. Services must bind
to `127.0.0.1`; remote access should use an authenticated tunnel.
