"""Command line: batch stacking and wavelet processing (the equivalent of RegiStax macros).

Examples:
    planstax-cli stack capture.ser -p Mak2 -o resultat.tif
    planstax-cli stack "D:/Jupiter/*.ser" -p Mak2 --wavelets
    planstax-cli batch D:/Captures D:/Images -p Mak2
    planstax-cli batch D:/Lune D:/Lune/images -p Mak2 --mosaic
    planstax-cli mosaic D:/Lune/images --brut -p Mak2 -o D:/Lune/lune.tif
    planstax-cli wavelets empile.tif -p Mak3
    planstax-cli presets --import-registax "C:/Program Files (x86)/RegiStax 6"
    planstax-cli demo demo.ser
    planstax-cli demo champs-lune --mosaic
    planstax-cli --lang en batch
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

from . import __version__
from .core import Cancelled, Pipeline, finish
from .i18n import LANGUAGES, set_language, tr
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
            print("  " + tr("erreur : {error}", error=exc))
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
        print("\n  " + tr("{stacked} images empilées, {points} points d'alignement, {seconds} s",
                          stacked=len(pipe.selected), points=len(pipe.points), seconds=f"{time.time() - t0:.1f}"))
        ext = "." + args.format
        out = _output_path(path, args.output, "_stack", ext, many)
        save_image(out, stacked, bits=args.bits)
        print("  " + tr("empilement : {path}", path=out))
        if args.wavelets:
            final = finish(stacked, settings)
            out_w = _output_path(path, args.output, "_ondelettes", ext, many, sibling=True)
            save_image(out_w, final, bits=args.bits)
            print("  " + tr("ondelettes : {path}", path=out_w))
    return status


def cmd_batch(args) -> int:
    from .batch import FORMATS, BatchOptions, is_done, list_videos, process_video
    from .paths import default_batch_folders
    default_in, default_out = default_batch_folders()
    in_dir, out_dir = args.input or default_in, args.output or default_out
    bits = next(b for _, ext, b in FORMATS if ext == args.format)
    opts = BatchOptions(save_final=not args.raw_only, save_raw=args.raw or args.raw_only,
                        fmt=args.format, bits=bits, skip_existing=not args.all, mosaic=args.mosaic)
    settings = _settings(args)
    videos = list_videos(in_dir)
    print(tr("Entrée : {folder} ({n} vidéo(s))\nSortie : {output}", folder=in_dir, n=len(videos), output=out_dir))
    errors = 0
    for path in videos:
        name = os.path.basename(path)
        if opts.skip_existing and is_done(path, out_dir, opts):
            print(tr("= {name} : déjà traitée", name=name))
            continue
        print(f"→ {name}")
        try:
            r = process_video(path, settings, out_dir, opts, _progress, workers=args.workers)
        except Cancelled:
            return 130
        except Exception as exc:  # noqa: BLE001 - one bad video must not stop the batch
            print("\n  " + tr("erreur : {error}", error=exc))
            errors += 1
            continue
        print("\n  " + tr("{stacked}/{frames} images empilées, {points} points d'alignement, {seconds} s → {names}",
                          stacked=r.stacked, frames=r.frames, points=r.points, seconds=f"{r.seconds:.0f}",
                          names=", ".join(os.path.basename(o) for o in r.outputs)))
        if not r.points:
            print("  " + tr("attention : aucun point d'alignement (vérifiez Luminosité min./max.)"))
    if opts.mosaic:
        from .batch import mosaic_sources, mosaic_suffix
        if _mosaic(mosaic_sources(videos, out_dir, opts), out_dir, opts.fmt, opts.bits,
                   suffix=mosaic_suffix(opts), workers=args.workers,
                   settings=settings if opts.save_final else None) is None:
            return 130
    return 1 if errors else 0


def _mosaic(paths: list[str], out_dir: str, fmt: str, bits: int, name: str | None = None,
            suffix: str = "", workers: int | None = None, settings: Settings | None = None):
    from .batch import MOSAIC_NAME, make_mosaics
    print(tr("Mosaïque de {n} image(s)", n=len(paths)))
    try:
        result = make_mosaics(paths, out_dir, fmt, bits, name or MOSAIC_NAME, suffix,
                              _progress, workers=workers, settings=settings)
    except Cancelled:
        return None
    print("\n" + result.plan.explain())
    for path in result.outputs:
        print(f"  → {path}")
    return result


def cmd_mosaic(args) -> int:
    from .batch import list_images
    if len(args.inputs) == 1 and os.path.isdir(args.inputs[0]):
        folder = args.inputs[0]
        paths = list_images(folder, raw=args.brut)
    else:
        paths = _expand(args.inputs)
        folder = os.path.dirname(os.path.abspath(paths[0])) if paths else "."
    settings = load_preset(args.preset) if args.preset else None
    fmt, name, suffix = args.format, None, "_brut" if args.brut and settings is None else ""
    out_dir = args.output or folder
    if args.output and os.path.splitext(args.output)[1] and not os.path.isdir(args.output):
        out_dir = os.path.dirname(os.path.abspath(args.output))
        name, ext = os.path.splitext(os.path.basename(args.output))
        fmt, suffix = ext[1:].lower(), ""  # the name asked for, as is
    result = _mosaic(paths, out_dir, fmt, args.bits, name, suffix, args.workers, settings)
    if result is None:
        return 130
    return 0 if result.outputs else 1


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
            print(tr("Aucun réglage RegiStax (wavelet-*.ini, estimate-*.ini…) dans ce dossier."))
            return 1
        print(tr("importés : {names}", names=", ".join(names)))
        print(tr("Ondelettes : gains laissés au neutre (formule des curseurs RegiStax non publique)."))
        for name in names:
            pos = registax_wavelet_positions(args.import_registax, name)
            if pos:
                print("  " + tr("positions RegiStax de {name} (10 = neutre) : {positions}", name=name, positions=pos))
    print(tr("Préréglages ({folder}) :", folder=presets_dir()))
    for name in list_presets():
        print(name)
    return 0


def cmd_demo(args) -> int:
    if args.mosaic:
        from .synth import cut_tiles, make_moon
        os.makedirs(args.output, exist_ok=True)
        tiles, _ = cut_tiles(make_moon(1500, 1500), 600, 450, seed=2)
        for k, tile in enumerate(tiles):
            save_image(os.path.join(args.output, f"lune_{k + 1}.tif"), tile)
        print(tr("{n} champs lunaires qui se recouvrent écrits dans : {folder}", n=len(tiles), folder=args.output))
        return 0
    from .synth import write_demo_ser
    write_demo_ser(args.output, n=args.frames, color=args.color)
    print(tr("Vidéo de démonstration écrite : {path}", path=args.output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="planstax-cli",
                                description=tr("Empilement et ondelettes pour l'imagerie planétaire."))
    p.add_argument("--version", action="version", version=f"PlanStax {__version__}")
    p.add_argument("--lang", choices=sorted(LANGUAGES), help=tr("langue des messages (fr, en, es)"))
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("inputs", nargs="+", help=tr("fichiers (jokers acceptés, ex. *.ser)"))
        sp.add_argument("-p", "--preset", help=tr("nom ou chemin d'un préréglage"))
        sp.add_argument("-o", "--output", help=tr("fichier ou dossier de sortie"))
        sp.add_argument("-f", "--format", default="tif", choices=["tif", "png", "fits", "jpg"])
        sp.add_argument("-b", "--bits", type=int, default=16, choices=[8, 16, 32])

    sp = sub.add_parser("stack", help=tr("aligner et empiler des vidéos"))
    common(sp)
    sp.add_argument("--wavelets", action="store_true", help=tr("enregistrer aussi la version traitée"))
    sp.add_argument("--percent", type=float, help=tr("pourcentage des meilleures images à garder"))
    sp.add_argument("--scale", type=float, help=tr("agrandissement de l'empilement (1, 1.5, 2)"))
    sp.add_argument("--bayer", choices=["RGGB", "GRBG", "GBRG", "BGGR"],
                    help=tr("forcer la matrice de Bayer"))
    sp.add_argument("--workers", type=int, help=tr("nombre de fils de calcul"))
    sp.set_defaults(func=cmd_stack)

    sp = sub.add_parser("batch", help=tr("traiter toutes les vidéos d'un dossier (une image par vidéo)"))
    sp.add_argument("input", nargs="?", help=tr("dossier des vidéos (défaut : dossier « input »)"))
    sp.add_argument("output", nargs="?", help=tr("dossier des images (défaut : dossier « output »)"))
    sp.add_argument("-p", "--preset", help=tr("nom ou chemin d'un préréglage"))
    sp.add_argument("-f", "--format", default="tif", choices=["tif", "png", "fits", "jpg"])
    sp.add_argument("--raw", action="store_true", help=tr("enregistrer aussi l'empilement brut"))
    sp.add_argument("--all", action="store_true", help=tr("retraiter aussi les vidéos déjà traitées"))
    sp.add_argument("--raw-only", action="store_true",
                    help=tr("n'enregistrer que l'empilement brut (sans ondelettes ni finitions)"))
    sp.add_argument("--mosaic", action="store_true",
                    help=tr("assembler les images en mosaïque, à partir des empilements bruts "
                            "(enregistrés aussi) : ondelettes image par image, niveaux et couleurs "
                            "sur la mosaïque entière (avec --raw-only : mosaïque brute)"))
    sp.add_argument("--workers", type=int, help=tr("nombre de fils de calcul"))
    sp.set_defaults(func=cmd_batch)

    sp = sub.add_parser("mosaic", help=tr("assembler en mosaïque des images qui se recouvrent"))
    sp.add_argument("inputs", nargs="+", help=tr("un dossier, ou des images (jokers acceptés)"))
    sp.add_argument("-o", "--output", help=tr("fichier ou dossier de sortie (défaut : mosaique.tif "
                                              "dans le dossier des images)"))
    sp.add_argument("-f", "--format", default="tif", choices=["tif", "png", "fits", "jpg"])
    sp.add_argument("-b", "--bits", type=int, default=16, choices=[8, 16, 32])
    sp.add_argument("--brut", action="store_true",
                    help=tr("dans un dossier, assembler les empilements bruts (« _brut »)"))
    sp.add_argument("-p", "--preset",
                    help=tr("appliquer les ondelettes et finitions d'un préréglage (images brutes) : "
                            "ondelettes image par image, niveaux et couleurs sur la mosaïque entière"))
    sp.add_argument("--workers", type=int, help=tr("nombre de fils de calcul"))
    sp.set_defaults(func=cmd_mosaic)

    sp = sub.add_parser("wavelets", help=tr("appliquer ondelettes et finitions à des images"))
    common(sp)
    sp.set_defaults(func=cmd_wavelets)

    sp = sub.add_parser("presets", help=tr("lister ou importer des préréglages"))
    sp.add_argument("--import-registax", metavar=tr("DOSSIER"),
                    help=tr("importer les réglages *-NOM.ini d'un dossier RegiStax 6"))
    sp.set_defaults(func=cmd_presets)

    sp = sub.add_parser("demo", help=tr("créer une vidéo SER de démonstration"))
    sp.add_argument("output")
    sp.add_argument("--frames", type=int, default=200)
    sp.add_argument("--color", action="store_true")
    sp.add_argument("--mosaic", action="store_true",
                    help=tr("écrire plutôt, dans le dossier indiqué, 9 champs lunaires qui se "
                            "recouvrent, pour essayer la mosaïque"))
    sp.set_defaults(func=cmd_demo)
    return p


def _language_option(argv: list[str]) -> str | None:
    """--lang read before the parser is built, so that its help is in that language too."""
    for k, a in enumerate(argv):
        if a == "--lang" and k + 1 < len(argv):
            return argv[k + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    set_language(_language_option(argv))
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n" + tr("Interrompu."))
        return 130


if __name__ == "__main__":
    sys.exit(main())
