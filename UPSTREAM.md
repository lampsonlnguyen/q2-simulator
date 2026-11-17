# Source provenance

Extracted from [lampsonlnguyen/q2-pod](https://github.com/lampsonlnguyen/q2-pod),
branch `desktop-simulator`, commit
[`49089f01b52ac2ce2fdd3c12f88031fd612c0d0b`](https://github.com/lampsonlnguyen/q2-pod/tree/49089f01b52ac2ce2fdd3c12f88031fd612c0d0b).
Q2 Pod's upstream project is [DiamondBond/q2-pod](https://github.com/DiamondBond/q2-pod).

- `emulation/` contains the simulator, MIPS runners, game ABI, launchers, documentation, and tests.
- `tools/art.py`, `tools/build.py`, `tools/ipod.py`, and `tools/theme.py` supply the existing theme drawing, asset decoding, font subsetting, and ELF helpers.
- `patch/` contains the game sources and headers, UI offsets, and UI audit data used by those helpers and the built-in game compiler.
- `assets/fonts/` and `assets/themes/` contain the preview fonts, their license notices, and theme definitions.
- `sources.list` provides the initial App Store catalog.
- `.github/workflows/emulation.yml` adapts the emulator workflow to this repository's `main` branch.

The imported files retain the original directory layout so their relative paths
work in this standalone checkout. The root launchers forward arguments to
`emulation/`. `requirements.txt` forwards to the simulator requirements.

The theme loader uses `patch/theme-payload-keys.json`, a snapshot of the exact
theme keys collected from the source revision's `theme_engine.c` and other
payload C files. This replaces scanning the complete firmware payload at
import time. Game logic, drawing helpers, and bundled theme values are copied
from the recorded source revision.

Build firmware packages in the Q2 Pod repository. The copied build module here
supplies emulator helpers and retains its upstream code for provenance.
