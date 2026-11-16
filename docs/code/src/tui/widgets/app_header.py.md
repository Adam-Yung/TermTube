# src/tui/widgets/app_header.py

Header strip: clock, title, busy spinner. `MainScreen` toggles the spinner through `set_status_loading`/`set_status_idle` from its worker counter (`_worker_start`/`_worker_end`, reference-counted so overlapping workers do not stop it early).

The clock shows minutes only. `on_mount` waits until the next minute boundary and then ticks every 60 s, so it does not lag by up to a minute.
