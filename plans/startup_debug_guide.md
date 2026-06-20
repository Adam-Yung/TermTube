---
name: mpv startup debug guide
overview: A comprehensive debugging script and guide to run on the target machine to identify exactly where mpv playback startup time is being spent.
todos: []
isProject: false
---

# mpv Startup Time Debugging Guide

Run all of the following on the target machine. Copy/paste the entire terminal output back.

---

## Step 1: Baseline binary execution times

Measures raw binary spawn cost (antivirus penalty shows here).

```bash
# Time the bundled yt-dlp version check
time ~/.local/termtube-deps/bin/yt-dlp --version

# Time it again (second run should be faster if AV caches approval)
time ~/.local/termtube-deps/bin/yt-dlp --version

# Time bundled mpv version
time timeout 5 ~/.local/termtube-deps/bin/mpv --no-config --no-video --version 2>/dev/null; echo "exit: $?"

# Time bundled mpv with a trivial direct URL (no ytdl, no network needed - just startup+quit)
time ~/.local/termtube-deps/bin/mpv --no-config --no-video --no-ytdl --idle=once --quit 2>/dev/null; echo "exit: $?"
```

---

## Step 2: Time URL resolution (yt-dlp --get-url)

This is what `resolve_stream_url()` does internally.

```bash
# Pick any video ID to test with (replace VIDEO_ID or use this default)
VIDEO_ID="dQw4w9WgXcQ"
COOKIES="$HOME/.config/TermTube/cookies.txt"
YTDLP="$HOME/.local/termtube-deps/bin/yt-dlp"

# Time audio URL resolution
echo "=== Audio URL resolution ==="
time $YTDLP --get-url -f "ba[format_note*=original]/ba" --no-warnings --cookies "$COOKIES" "https://www.youtube.com/watch?v=$VIDEO_ID"

# Time video+audio URL resolution
echo "=== Video+Audio URL resolution ==="
time $YTDLP --get-url -f "bv+(ba[format_note*=original]/ba)" --no-warnings --cookies "$COOKIES" "https://www.youtube.com/watch?v=$VIDEO_ID"

# Run audio resolution again to see if second run is faster (YouTube API caching)
echo "=== Audio URL resolution (2nd run) ==="
time $YTDLP --get-url -f "ba[format_note*=original]/ba" --no-warnings --cookies "$COOKIES" "https://www.youtube.com/watch?v=$VIDEO_ID"
```

---

## Step 3: Time mpv with a pre-resolved direct URL

This isolates mpv's startup from yt-dlp's resolution time.

```bash
# First get a resolved URL
AUDIO_URL=$($YTDLP --get-url -f "ba[format_note*=original]/ba" --no-warnings --cookies "$COOKIES" "https://www.youtube.com/watch?v=$VIDEO_ID" 2>/dev/null)
echo "Resolved URL length: ${#AUDIO_URL}"
echo "URL starts with: ${AUDIO_URL:0:80}"

# Time mpv startup with the pre-resolved URL (should be near-instant)
echo "=== mpv with direct URL (audio, --no-ytdl) ==="
time timeout 10 ~/.local/termtube-deps/bin/mpv \
  --no-config --no-video --no-ytdl --force-window=no --no-terminal \
  --start=0 --end=2 \
  "$AUDIO_URL" 2>&1 | head -5
echo "exit: $?"

# For comparison: time mpv with YouTube URL (uses ytdl_hook internally)
echo "=== mpv with YouTube URL (ytdl_hook, for comparison) ==="
time timeout 30 ~/.local/termtube-deps/bin/mpv \
  --no-config --no-video --force-window=no --no-terminal \
  --ytdl-format="ba[format_note*=original]/ba" \
  --ytdl-raw-options="cookies=$COOKIES" \
  --start=0 --end=2 \
  "https://www.youtube.com/watch?v=$VIDEO_ID" 2>&1 | head -5
echo "exit: $?"
```

---

## Step 4: mpv verbose startup log

Shows exactly where mpv spends time during startup.

```bash
echo "=== mpv verbose log with direct URL ==="
timeout 10 ~/.local/termtube-deps/bin/mpv \
  --no-config --no-video --no-ytdl --force-window=no \
  --msg-level=all=v \
  --start=0 --end=2 \
  "$AUDIO_URL" 2>&1 | head -50

echo ""
echo "=== mpv verbose log with YouTube URL ==="
timeout 30 ~/.local/termtube-deps/bin/mpv \
  --no-config --no-video --force-window=no \
  --msg-level=all=v \
  --ytdl-format="ba[format_note*=original]/ba" \
  --ytdl-raw-options="cookies=$COOKIES" \
  --start=0 --end=2 \
  "https://www.youtube.com/watch?v=$VIDEO_ID" 2>&1 | head -80
```

---

## Step 5: TermTube debug mode (in-app timing)

Run the app with `--debug` to get internal timing logs.

```bash
# Launch TermTube in debug mode
~/.local/bin/termtube --debug

# After playing one song (just start audio on any video, wait for it to play
# for a few seconds, then quit the app with 'q'), the log file will be at:
echo "=== Debug log location ==="
ls -lt /tmp/TermTube/*.log 2>/dev/null || ls -lt "$TMPDIR/TermTube/"*.log 2>/dev/null

# Print the relevant section of the log (URL resolution + mpv launch)
echo "=== Relevant log entries ==="
LOG=$(ls -t /tmp/TermTube/*.log 2>/dev/null | head -1)
if [ -z "$LOG" ]; then
  LOG=$(ls -t "$TMPDIR/TermTube/"*.log 2>/dev/null | head -1)
fi
grep -E "resolve_stream_url|audio pre-resolved|audio mpv cmd|_mpv_exe|_launch_audio" "$LOG"
```

---

## Step 6: Check which mpv binary is actually being used

```bash
echo "=== Binary paths ==="
echo "Bundled mpv: $(ls -la ~/.local/termtube-deps/bin/mpv 2>/dev/null)"
echo "System mpv:  $(which mpv 2>/dev/null)"
echo "Bundled yt-dlp: $(ls -la ~/.local/termtube-deps/bin/yt-dlp 2>/dev/null)"
echo "System yt-dlp:  $(which yt-dlp 2>/dev/null)"

echo ""
echo "=== Binary versions ==="
~/.local/termtube-deps/bin/mpv --no-config --version 2>/dev/null | head -1
~/.local/termtube-deps/bin/yt-dlp --version

echo ""
echo "=== PATH order (first 5 entries) ==="
echo "$PATH" | tr ':' '\n' | head -5

echo ""
echo "=== mpv dylib loading (check for missing libs) ==="
otool -L ~/.local/termtube-deps/bin/mpv 2>/dev/null | head -20
```

---

## Step 7: Network latency baseline

```bash
echo "=== DNS resolution ==="
time nslookup rr3---sn-5hne6nzr.googlevideo.com 2>/dev/null | grep -E "Address|Name"

echo ""
echo "=== YouTube API latency ==="
time curl -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s (DNS: %{time_namelookup}s, connect: %{time_connect}s, TLS: %{time_appconnect}s, first_byte: %{time_starttransfer}s)" \
  "https://www.youtube.com/watch?v=$VIDEO_ID"
echo ""
```

---

## Step 8: Full end-to-end timed pipeline

This simulates exactly what TermTube does internally:

```bash
echo "=== Full pipeline simulation ==="
echo ""

T0=$(python3 -c "import time; print(time.time())")

echo "1. Resolving audio URL..."
T1=$(python3 -c "import time; print(time.time())")
AUDIO_URL2=$($YTDLP --get-url -f "ba[format_note*=original]/ba" --no-warnings --cookies "$COOKIES" "https://www.youtube.com/watch?v=$VIDEO_ID" 2>/dev/null)
T2=$(python3 -c "import time; print(time.time())")

echo "2. Launching mpv with direct URL..."
T3=$(python3 -c "import time; print(time.time())")
timeout 5 ~/.local/termtube-deps/bin/mpv \
  --no-config --no-video --no-ytdl --force-window=no --no-terminal \
  --msg-level=all=error \
  --cache=yes --demuxer-max-bytes=150M --demuxer-readahead-secs=30 \
  --start=0 --end=2 \
  "$AUDIO_URL2" 2>/dev/null &
MPV_PID=$!

# Wait for mpv to actually start playing (poll for audio output)
sleep 0.5
T4=$(python3 -c "import time; print(time.time())")
wait $MPV_PID 2>/dev/null
T5=$(python3 -c "import time; print(time.time())")

python3 -c "
t0, t1, t2, t3, t4, t5 = $T0, $T1, $T2, $T3, $T4, $T5
print()
print('=== TIMING BREAKDOWN ===')
print(f'  URL resolution:  {t2-t1:.2f}s')
print(f'  mpv spawn→0.5s:  {t4-t3:.2f}s')
print(f'  mpv total run:   {t5-t3:.2f}s')
print(f'  TOTAL pipeline:  {t5-t0:.2f}s')
print()
print('INTERPRETATION:')
if t2-t1 > 3:
    print(f'  >> URL resolution is the bottleneck ({t2-t1:.1f}s)')
    print(f'     This is yt-dlp + YouTube API latency')
elif t5-t3 > 5:
    print(f'  >> mpv startup is the bottleneck ({t5-t3:.1f}s)')
    print(f'     Check Step 4 verbose logs for where mpv stalls')
else:
    print(f'  >> Both stages look reasonable')
    print(f'     Total {t5-t0:.1f}s may be dominated by AV scanning')
"
```

---

## What to send back

After running ALL steps above, copy the full terminal output and paste it back. Key things I'll look for:

1. **Step 1** — Is the binary spawn itself slow? (AV penalty baseline)
2. **Step 2** — Is yt-dlp URL resolution the bottleneck?
3. **Step 3** — Is mpv fast with a direct URL? If yes, the fix is working.
4. **Step 4** — mpv verbose logs show exactly which init stage is slow
5. **Step 5** — Does the app log show pre-resolution succeeding or falling back?
6. **Step 8** — Overall pipeline timing breakdown
