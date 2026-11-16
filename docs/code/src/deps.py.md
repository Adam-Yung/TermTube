# src/deps.py

Startup gate: confirms `deno`, `mpv` and `ffmpeg` exist in the managed bin dir (`plat.is_tool_installed`), and offers to install what is missing through `src/bootstrap.py`. Also prints the `--browser-help` text.

## Invariants

- Only the managed bin dir counts, as `AGENTS.md` requires: a system `mpv` does not satisfy the check, and the install offer follows. The missing list names the directory it looked in.
- With no TTY on stdin the function never prompts: it prints the manual hint and returns False (the app exits 1).
- After a successful install in the same process, `PATH` is not refreshed. The tools are found on the next launch, or by direct path where the code asks `get_deps_bin()`.

## Interface

- `check_dependencies()` is called once from `main.py`. `print_cookies_help()` is called for `--browser-help`; its text must stay in step with the browser options in [docs/decisions/cookies-and-auth.md](../../decisions/cookies-and-auth.md).
