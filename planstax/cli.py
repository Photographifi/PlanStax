"""Command line: batch stacking and wavelet processing (the equivalent of RegiStax macros).

Examples:
    planstax-cli stack capture.ser -p Mak2 -o resultat.tif
    planstax-cli stack "D:/Jupiter/*.ser" -p Mak2 --wavelets
    planstax-cli batch D:/Captures D:/Images -p Mak2
    planstax-cli wavelets empile.tif -p Mak3
    planstax-cli presets --import-registax "C:/Program Files (x86)/RegiStax 6"
    planstax-cli demo demo.ser
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

from . import __version__
from .core import Cancelled, Pipeline, finish
from .io import open_source, read_image, save_image
from .settings import (Settings, import_all_registax, list_presets, load_preset, presets_dir,
                       registax_wavelet_positions)


def _progress(fraction: float, message: str) -> None:
    if sys.stdout is None:  # started without a console (pythonw / PlanStax.exe --cli)
        return
    bar = "#" * int(fraction * 30)
    sys.stdout.write(f"\r  [{bar:<30}] {fraction * 100:5.1f} %  {message:<45}")
    sys.stdout.flush()


def _expand(patterns: list[str]) -> list[str]:
    files: list[str] = []
    for p in patterns:
        matches = sorted(glob.glob(p))
        files.extend(matches if matches else [p])
    return files


def _settings(args) -> Settings:
    return load_preset(args.preset) if args.preset else Settings()


def _output_path(src: str, out: str | None, suffix: str, ext: str, many: bool,
                 sibling: bool = False) -> str:
    """Where to write the result for `src`. `out` may be a folder (existing, or any path
    without an extension) or an explicit file; `sibling` derives a second file name from
    an explicit one (e.g. result.tif → result_ondelettes.tif)."""
    base = os.path.splitext(os.path.basename(src))[0] + suffix + ext
    if not out:
        return os.path.join(os.path.dirname(os.path.abspath(src)), base)
    if many or os.path.isdir(out) or not os.path.splitext(out)[1]:
        os.makedirs(out, exist_ok=True)
        return os.path.join(out, base)
    if sibling:
        root, e = os.path.splitext(out)
        return root + suffix + e
    return out


def cmd_stack(args) -> int:
    settings = _settings(args)
    if args.percent is not None:
        settings.limit.method, settings.limit.percent = "percent", args.percent
    if args.scale is not None:
        settings.stack.scale = args.scale
    files = _expand(args.inputs)
    many = len(files) > 1
    status = 0
    for path in files:
        print(f"→ {path}")
        try:
            src = open_source(path, args.bayer)
        except (OSError, ValueError) as exc:
            print(f"  erreur : {exc}")
            status = 1
            continue
        print(f"  {src.describe()}")
        t0 = time.time()
        try:
            pipe = Pipeline(src, settings, workers=args.workers)
            stacked = pipe.run_all(_progress)
        except Cancelled:
            return 130
        finally:
            src.close()
        print(f"\n  {len(pipe.selected)} images empilées, {len(pipe.points)} points d'alignement, "
              f"{time.time() - t0:.1f} s")
        ext = "." + args.format
        out = _output_path(path, args.output, "_stack", ext, many)
        save_image(out, stacked, bits=args.bits)
        print(f"  empilement : {out}")
        if args.wavelets:
            final = finish(stacked, settings)
            out_w = _output_path(path, args.output, "_ondelettes", ext, many, sibling=True)
            save_image(out_w, final, bits=args.bits)
            print(f"  ondelettes : {out_w}")
    return status


def cmd_batch(args) -> int:
    from .batch import FORMATS, BatchOptions, is_done, list_videos, process_video
    from .paths import default_batch_folders
    default_in, default_out = default_batch_folders()
    in_dir, out_dir = args.input or default_in, args.output or default_out
    bits = next(b for _, ext, b in FORMATS if ext == args.format)
    opts = BatchOptions(save_raw=args.raw, fmt=args.format, bits=bits,
                        skip_existing=not args.all)
    settings = _settings(args)
    videos = list_videos(in_dir)
    print(f"Entrée : {in_dir} ({len(videos)} vidéo(s))\nSortie : {out_dir}")
    errors = 0
    for path in videos:
        name = os.path.basename(path)
        if opts.skip_existing and is_done(path, out_dir, opts):
            print(f"= {name} : déjà traitée")
            continue
        print(f"→ {name}")
        try:
            r = process_video(path, settings, out_dir, opts, _progress, workers=args.workers)
        except Cancelled:
            return 130
        except Exception as exc:  # noqa: BLE001 - one bad video must not stop the batch
            print(f"\n  erreur : {exc}")
            errors += 1
            continue
        print(f"\n  {r.stacked}/{r.frames} images empilées, {r.points} points d'alignement, "
              f"{r.seconds:.0f} s → " + ", ".join(os.path.basename(o) for o in r.outputs))
        if not r.points:
            print("  attention : aucun point d'alignement (vérifiez Luminosité min./max.)")
    return 1 if errors else 0


def cmd_wavelets(args) -> int:
    settings = _settings(args)
    files = _expand(args.inputs)
    many = len(files) > 1
    for path in files:
        img = read_image(path)
        out = _output_path(path, args.output, "_ondelettes", "." + args.format, many)
        save_image(out, finish(img, settings), bits=args.bits)
        print(f"{path} → {out}")
    return 0


def cmd_presets(args) -> int:
    if args.import_registax:
        names = import_all_registax(args.import_registax)
        if not names:
            print("Aucun réglage RegiStax (wavelet-*.ini, estimate-*.ini…) dans ce dossier.")
            return 1
        print("importés : " + ", ".join(names))
        print("Ondelettes : gains laissés au neutre (formule des curseurs RegiStax non publique).")
        for name in names:
            pos = registax_wavelet_positions(args.import_registax, name)
            if pos:
                print(f"  positions RegiStax de {name} (10 = neutre) : {pos}")
    print(f"Préréglages ({presets_dir()}) :")
    for name in list_presets():
        print(name)
    return 0


def cmd_demo(args) -> int:
    from .synth import write_demo_ser
    write_demo_ser(args.output, n=args.frames, color=args.color)
    print(f"Vidéo de démonstration écrite : {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="planstax-cli",
                                description="Empilement et ondelettes pour l'imagerie planétaire.")
    p.add_argument("--version", action="version", version=f"PlanStax {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("inputs", nargs="+", help="fichiers (jokers acceptés, ex. *.ser)")
        sp.add_argument("-p", "--preset", help="nom ou chemin d'un préréglage")
        sp.add_argument("-o", "--output", help="fichier ou dossier de sortie")
        sp.add_argument("-f", "--format", default="tif", choices=["tif", "png", "fits", "jpg"])
        sp.add_argument("-b", "--bits", type=int, default=16, choices=[8, 16, 32])

    sp = sub.add_parser("stack", help="aligner et empiler des vidéos")
    common(sp)
    sp.add_argument("--wavelets", action="store_true", help="enregistrer aussi la version traitée")
    sp.add_argument("--percent", type=float, help="pourcentage des meilleures images à garder")
    sp.add_argument("--scale", type=float, help="agrandissement de l'empilement (1, 1.5, 2)")
    sp.add_argument("--bayer", choices=["RGGB", "GRBG", "GBRG", "BGGR"],
                    help="forcer la matrice de Bayer")
    sp.add_argument("--workers", type=int, help="nombre de fils de calcul")
    sp.set_defaults(func=cmd_stack)

    sp = sub.add_parser("batch", help="traiter toutes les vidéos d'un dossier (une image par vidéo)")
    sp.add_argument("input", nargs="?", help="dossier des vidéos (défaut : dossier « input »)")
    sp.add_argument("output", nargs="?", help="dossier des images (défaut : dossier « output »)")
    sp.add_argument("-p", "--preset", help="nom ou chemin d'un préréglage")
    sp.add_argument("-f", "--format", default="tif", choices=["tif", "png", "fits", "jpg"])
    sp.add_argument("--raw", action="store_true", help="enregistrer aussi l'empilement brut")
    sp.add_argument("--all", action="store_true", help="retraiter aussi les vidéos déjà traitées")
    sp.add_argument("--workers", type=int, help="nombre de fils de calcul")
    sp.set_defaults(func=cmd_batch)

    sp = sub.add_parser("wavelets", help="appliquer ondelettes et finitions à des images")
    common(sp)
    sp.set_defaults(func=cmd_wavelets)

    sp = sub.add_parser("presets", help="lister ou importer des préréglages")
    sp.add_argument("--import-registax", metavar="DOSSIER",
                    help="importer les réglages *-NOM.ini d'un dossier RegiStax 6")
    sp.set_defaults(func=cmd_presets)

    sp = sub.add_parser("demo", help="créer une vidéo SER de démonstration")
    sp.add_argument("output")
    sp.add_argument("--frames", type=int, default=200)
    sp.add_argument("--color", action="store_true")
    sp.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrompu.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
