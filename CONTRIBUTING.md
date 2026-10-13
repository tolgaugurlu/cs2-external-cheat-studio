# Contributing

Use Windows x64 and Python 3.11. Install `requirements-dev.txt` in a virtual environment, then run `python -m unittest discover -s tests -q`. UI changes should also pass `python tools/check_studio_layout.py` and be reviewed in `python memory_bot.py --demo`.

Keep tests independent of live game memory, real input, local offset dumps and personal settings. Test state transitions, cleanup and persistence failure cases. Keep setup secrets generated per machine and excluded from Git.

Preserve attribution and licenses. Do not commit game files, binaries, offset caches, logs, personal profiles or tokens. Reports should state the app revision and relevant behavior without uploading unreviewed local files.

Describe observed behavior and verification limits accurately. Do not label builds VAC-safe, undetectable or guaranteed to hit. Functional tests cannot establish those claims.
