PlanStax {version} for Linux — stacking and wavelets for planetary imaging
============================================================================

First Linux version: it has not yet been tried on any real Linux. Please report any problem,
copying what the terminal shows.

WHAT YOU NEED
  64-bit Linux (x86_64 or ARM64 PC), Python 3.10 or newer, and an Internet connection on the
  first start (about 150 MB of libraries, downloaded only once).

  System packages to install first, depending on the distribution:
    Ubuntu, Debian, Linux Mint:  sudo apt install python3 python3-venv libxcb-cursor0
    Fedora:                      sudo dnf install python3 xcb-util-cursor
    Arch, Manjaro:               sudo pacman -S python xcb-util-cursor
    openSUSE:                    sudo zypper install python3 libxcb-cursor0

INSTALLATION
  1. Unzip the archive, for instance in your home folder:
       unzip PlanStax-{version}-Linux.zip
  2. Start PlanStax from a terminal:
       cd PlanStax
       chmod +x planstax.sh       (if needed)
       ./planstax.sh
     The first start installs the libraries in the .venv subfolder, then opens the window.
     The next times, the window opens straight away.

USE
  ./planstax.sh                 opens the interface
  ./planstax.sh video.ser       opens the interface with a video (SER, AVI, MP4…)

  In the interface:
    1. Ctrl+O: open a video (or drop it in the window).
    2. F5 "Do all": alignment, selection of the best frames, stacking.
    3. Wavelets tab: raise the sharpening of layers 1 to 3 (30 to 50 to begin with).
    4. Finishing tab: automatic RGB alignment, colour balance, levels,
       orientation (quarter turns, mirrors, fine rotation of ±90° by tenths of a degree).
    5. Ctrl+S: save (16-bit TIFF advised).

  Language: French, English or Spanish, following the system. To change it: View menu >
  "Langue / Language / Idioma", then restart. On the command line:
       ./planstax.sh --lang en batch

  Several videos at once: put them in the "input" folder (created next to planstax.sh), then
  File > Batch processing (Ctrl+L) > Start; one image per video is written to "output".
  On the command line:
       ./planstax.sh batch                         (input → output folders)
       ./planstax.sh batch ~/Captures ~/Images     (other folders)

  Mosaic (Moon, Sun, landscape shot in several fields, with about 25 % of overlap): tick
  "Assemble the images into a mosaic" in the batch processing window, or File > Assemble a
  mosaic (Ctrl+M). On the command line:
       ./planstax.sh batch --mosaic                (output/mosaique.tif at the end of the batch)
       ./planstax.sh mosaic ~/Images/Moon          (images already made)

  Settings and presets: ~/.config/PlanStax

IF SOMETHING GOES WRONG
  - "Could not load the Qt platform plugin "xcb"": install the libxcb-cursor package given
    above for your distribution.
  - Under Wayland, if the window does not show, try:
       QT_QPA_PLATFORM=xcb ./planstax.sh
  - To install everything again: delete the .venv subfolder, then run ./planstax.sh again.
  - To use another Python:  PYTHON=python3.12 ./planstax.sh

UNINSTALLING
  Delete the PlanStax folder and, if you wish, ~/.config/PlanStax.

ABOUT
  PlanStax is free software (MIT licence, © 2026 Photographifi), written in Python with
  NumPy, OpenCV, Qt (PySide6) and tifffile. It has no link with RegiStax nor its author.
