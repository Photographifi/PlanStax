PlanStax {version} — stacking and wavelets for planetary imaging
==================================================================

INSTALLATION (nothing to install)
  1. Right-click the .zip file > "Extract All…" > Extract.
     Important: do not start the program from inside the .zip.
  2. In the extracted folder, double-click PlanStax.exe.
     The first start may take about ten seconds.
  3. To have it on the Desktop: Help menu > "Create a shortcut on the Desktop".

  The PlanStax folder can be kept wherever you like (Documents, USB stick…).
  To uninstall: simply delete the folder.

USE IN 5 STEPS
  1. Ctrl+O: open a SER or AVI video (or drop it in the window).
  2. F5 "Do all": alignment, selection of the best frames, stacking.
  3. Wavelets tab: raise the sharpening of layers 1 to 3 (30 to 50 to begin
     with); a little denoising on layers 1-2 if noise shows.
  4. Finishing tab: automatic RGB alignment, colour balance, levels,
     orientation (quarter turns, mirrors and fine rotation of ±90° by tenths of a degree).
  5. Ctrl+S: save (16-bit TIFF advised).

  Key B: compare before/after · F: fit to window · F1: quick guide.

LANGUAGE
  PlanStax shows in French, English or Spanish, following the language of Windows.
  To change it: View menu > "Langue / Language / Idioma", then restart.

SEVERAL VIDEOS AT ONCE (batch processing)
  1. Put the videos in the "input" folder (next to PlanStax.exe).
  2. In PlanStax: File > Batch processing (Ctrl+L) > Start.
  3. One image per video is written to the "output" folder.
  First set up one video by hand (wavelets included): the batch applies the current
  settings, or the preset chosen in the batch processing window.

MOSAIC (Moon, Sun, landscape shot in several fields)
  Tick "Assemble the images into a mosaic" in the batch processing window: at the
  end, the overlapping images are assembled into output\mosaique.tif.
  The wavelets are applied image by image, the levels and colours only once, to the
  whole mosaic: no different zones in the sky.
  For images already made: File > Assemble a mosaic (Ctrl+M).
  Plan about 25 % of overlap between neighbouring fields.

IF SOMETHING GOES WRONG
  - If Windows shows "Windows protected your PC": click "More info", then
    "Run anyway".
  - If the program will not start, a message says so and the details are saved
    in %APPDATA%\PlanStax\erreur-demarrage.txt
    (to send to the person who gave you PlanStax).

REQUIREMENTS
  Windows 10 or 11, 64-bit. 8 GB of memory advised for large videos.

ABOUT
  PlanStax is free software (MIT licence), written in Python. PlanStax.exe is
  the official Python interpreter (signed by the Python Software Foundation),
  renamed; the program itself is in runtime\site-packages\planstax.
  Libraries included: Python, NumPy, OpenCV, Qt (PySide6), tifffile; their licences
  are in the matching folders.
