# src/deps.py

Startup gate: confirms `deno`, `mpv` and `ffmpeg` resolve with `shutil.which`, and offers to install what is missing through `src/bootstrap.py`. Also prints the `--browser-help` text.

## Invariants

- The check relies on `src/main.py` having prepended the managed deps bin to `PATH` before this runs. A system `mpv` therefore still satisfies the check when the managed dir has none. That conflicts with the "bundled tools only" rule in `AGENTS.md`; `bootstrap.is_tool_installed` is the strict check.
- With no TTY on stdin the function never prompts: it prints the manual hint and returns False (the app exits 1).
- After a successful install in the same process, `PATH` is not refreshed. The tools are found on the next launch, or by direct path where the code asks `get_deps_bin()`.

## Interface

- `check_dependencies()` is called once from `main.py`. `print_cookies_help()` is called for `--browser-help`; its text must stay in step with the browser options in [docs/decisions/cookies-and-auth.md](../../decisions/cookies-and-auth.md).
