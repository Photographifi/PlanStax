PlanStax {version} for Mac — stacking and wavelets for planetary imaging
==========================================================================

First Mac version: it has not yet been tried on any real Mac. Please report any problem,
copying what the Terminal window shows.

WHAT YOU NEED
  macOS 12 (Monterey) or newer, Apple Silicon Mac (M1, M2, M3, M4…) or Intel.
  Python 3.13, to install once from https://www.python.org/downloads/macos/
  ("macOS 64-bit universal2 installer"). The Python shipped with macOS is too old.
  An Internet connection on the first start (about 150 MB of libraries, downloaded only
  once).

INSTALLATION
  1. Double-click the .zip archive: the PlanStax folder appears (usually in Downloads).
     Keep it wherever you like, for instance in your home folder.
  2. First start, from the Terminal (Applications > Utilities > Terminal): type
       bash
     followed by a space, drag the PlanStax.command file of the folder into the Terminal
     window, then press Return.
     The Terminal installs the libraries (a few minutes), then the PlanStax window opens.
  3. The next times: simply double-click PlanStax.command.

  Why go through the Terminal the first time? macOS (Gatekeeper) refuses to open with a
  double-click a downloaded file that does not come from a developer registered with Apple.
  After this first start, PlanStax lifts this block on its own folder.
  Another way: double-click PlanStax.command, decline, then open System Settings > Privacy
  & Security and click "Open Anyway".

USE
  1. ⌘O: open a SER, AVI, MP4… video (or drop it in the window).
  2. F5 "Do all": alignment, selection of the best frames, stacking.
  3. Wavelets tab: raise the sharpening of layers 1 to 3 (30 to 50 to begin with).
  4. Finishing tab: automatic RGB alignment, colour balance, levels,
     orientation (quarter turns, mirrors, fine rotation of ±90° by tenths of a degree).
  5. ⌘S: save (16-bit TIFF advised).
  On the reference image: ⌘ + click adds an alignment point, Shift + click removes it.

  Language: French, English or Spanish, following macOS. To change it: View menu >
  "Langue / Language / Idioma", then restart PlanStax.

  Several videos at once: put them in the "input" folder (created next to
  PlanStax.command), then File > Batch processing (⌘L) > Start; one image per video is
  written to "output".

  Mosaic (Moon, Sun, landscape shot in several fields, with about 25 % of overlap): tick
  "Assemble the images into a mosaic" in the batch processing window, or File > Assemble a
  mosaic (⇧⌘M).

  The Terminal window stays open while PlanStax runs: this is normal, do not close it (you
  can close it after quitting PlanStax).

  Settings and presets: ~/Library/Application Support/PlanStax

IF SOMETHING GOES WRONG
  - "Python 3.10 or newer cannot be found": install Python 3.13 (see above), then start
    again.
  - To install everything again: delete the hidden .venv subfolder (in the Terminal:
    rm -rf ~/path/to/PlanStax/.venv), then start again.

UNINSTALLING
  Delete the PlanStax folder and, if you wish,
  ~/Library/Application Support/PlanStax.

ABOUT
  PlanStax is free software (MIT licence, © 2026 Photographifi), written in Python with
  NumPy, OpenCV, Qt (PySide6) and tifffile. It has no link with RegiStax nor its author.
