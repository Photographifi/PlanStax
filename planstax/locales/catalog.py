"""Translations of every interface text: French (as written in the code) → (English, Spanish).

Keep the {placeholders} unchanged; tests/test_i18n.py checks that every text of the code is here
and that the placeholders match. To list what is missing:
    .venv\\Scripts\\python.exe packaging\\extract_texts.py --missing
"""

TRANSLATIONS = {
    # ------------------------------------------------------------------ portable launcher
    "PlanStax n'a pas pu démarrer :\n\n{error}\n\nDétails enregistrés dans :\n{log}": (
        "PlanStax could not start:\n\n{error}\n\nDetails saved in:\n{log}",
        "PlanStax no ha podido arrancar:\n\n{error}\n\nDetalles guardados en:\n{log}"),

    # ------------------------------------------------------------------ formats, batch
    "TIFF 16 bits": ("16-bit TIFF", "TIFF de 16 bits"),
    "PNG 16 bits": ("16-bit PNG", "PNG de 16 bits"),
    "FITS 32 bits flottant": ("32-bit float FITS", "FITS de 32 bits en coma flotante"),
    "JPEG": ("JPEG", "JPEG"),
    "aucune mosaïque": ("no mosaic", "ningún mosaico"),
    "{name} ({n} images)": ("{name} ({n} images)", "{name} ({n} imágenes)"),

    # ------------------------------------------------------------------ command line
    "erreur : {error}": ("error: {error}", "error: {error}"),
    "{stacked} images empilées, {points} points d'alignement, {seconds} s": (
        "{stacked} frames stacked, {points} alignment points, {seconds} s",
        "{stacked} imágenes apiladas, {points} puntos de alineación, {seconds} s"),
    "empilement : {path}": ("stack: {path}", "apilado: {path}"),
    "ondelettes : {path}": ("wavelets: {path}", "ondículas: {path}"),
    "Entrée : {folder} ({n} vidéo(s))\nSortie : {output}": (
        "Input: {folder} ({n} video(s))\nOutput: {output}",
        "Entrada: {folder} ({n} vídeo(s))\nSalida: {output}"),
    "= {name} : déjà traitée": ("= {name}: already processed", "= {name}: ya procesado"),
    "{stacked}/{frames} images empilées, {points} points d'alignement, {seconds} s → {names}": (
        "{stacked}/{frames} frames stacked, {points} alignment points, {seconds} s → {names}",
        "{stacked}/{frames} imágenes apiladas, {points} puntos de alineación, {seconds} s → {names}"),
    "attention : aucun point d'alignement (vérifiez Luminosité min./max.)": (
        "warning: no alignment point (check Min./Max. brightness)",
        "atención: ningún punto de alineación (revise Brillo mín./máx.)"),
    "Mosaïque de {n} image(s)": ("Mosaic of {n} image(s)", "Mosaico de {n} imagen(es)"),
    "Aucun réglage RegiStax (wavelet-*.ini, estimate-*.ini…) dans ce dossier.": (
        "No RegiStax settings (wavelet-*.ini, estimate-*.ini…) in this folder.",
        "Ningún ajuste de RegiStax (wavelet-*.ini, estimate-*.ini…) en esta carpeta."),
    "importés : {names}": ("imported: {names}", "importados: {names}"),
    "Ondelettes : gains laissés au neutre (formule des curseurs RegiStax non publique).": (
        "Wavelets: gains left neutral (the formula of the RegiStax sliders is not public).",
        "Ondículas: ganancias en neutro (la fórmula de los cursores de RegiStax no es pública)."),
    "positions RegiStax de {name} (10 = neutre) : {positions}": (
        "RegiStax positions of {name} (10 = neutral): {positions}",
        "posiciones RegiStax de {name} (10 = neutro): {positions}"),
    "Préréglages ({folder}) :": ("Presets ({folder}):", "Preajustes ({folder}):"),
    "{n} champs lunaires qui se recouvrent écrits dans : {folder}": (
        "{n} overlapping lunar fields written to: {folder}",
        "{n} campos lunares que se solapan escritos en: {folder}"),
    "Vidéo de démonstration écrite : {path}": ("Demo video written: {path}", "Vídeo de demostración escrito: {path}"),
    "Empilement et ondelettes pour l'imagerie planétaire.": (
        "Stacking and wavelets for planetary imaging.",
        "Apilado y ondículas para la imagen planetaria."),
    "langue des messages (fr, en, es)": ("language of the messages (fr, en, es)", "idioma de los mensajes (fr, en, es)"),
    "fichiers (jokers acceptés, ex. *.ser)": ("files (wildcards accepted, e.g. *.ser)", "archivos (se aceptan comodines, p. ej. *.ser)"),
    "fichier ou dossier de sortie": ("output file or folder", "archivo o carpeta de salida"),
    "aligner et empiler des vidéos": ("align and stack videos", "alinear y apilar vídeos"),
    "enregistrer aussi la version traitée": ("also save the processed version", "guardar también la versión procesada"),
    "pourcentage des meilleures images à garder": ("percentage of the best frames to keep", "porcentaje de las mejores imágenes que se conservan"),
    "agrandissement de l'empilement (1, 1.5, 2)": ("enlargement of the stack (1, 1.5, 2)", "ampliación del apilado (1, 1.5, 2)"),
    "forcer la matrice de Bayer": ("force the Bayer matrix", "forzar la matriz de Bayer"),
    "nombre de fils de calcul": ("number of computing threads", "número de hilos de cálculo"),
    "traiter toutes les vidéos d'un dossier (une image par vidéo)": (
        "process every video of a folder (one image per video)",
        "procesar todos los vídeos de una carpeta (una imagen por vídeo)"),
    "dossier des vidéos (défaut : dossier « input »)": (
        "folder of the videos (default: \"input\" folder)",
        "carpeta de los vídeos (por defecto: carpeta «input»)"),
    "dossier des images (défaut : dossier « output »)": (
        "folder of the images (default: \"output\" folder)",
        "carpeta de las imágenes (por defecto: carpeta «output»)"),
    "nom ou chemin d'un préréglage": ("name or path of a preset", "nombre o ruta de un preajuste"),
    "enregistrer aussi l'empilement brut": ("also save the raw stack", "guardar también el apilado en bruto"),
    "retraiter aussi les vidéos déjà traitées": ("process again the videos already processed", "volver a procesar también los vídeos ya procesados"),
    "n'enregistrer que l'empilement brut (sans ondelettes ni finitions)": (
        "only save the raw stack (no wavelets nor finishing)",
        "guardar solo el apilado en bruto (sin ondículas ni acabado)"),
    "assembler les images en mosaïque, à partir des empilements bruts (enregistrés aussi) : ondelettes image par image, niveaux et couleurs sur la mosaïque entière (avec --raw-only : mosaïque brute)": (
        "assemble the images into a mosaic, from the raw stacks (saved as well): wavelets image by image, "
        "levels and colours on the whole mosaic (with --raw-only: raw mosaic)",
        "montar las imágenes en un mosaico, a partir de los apilados en bruto (guardados también): ondículas "
        "imagen por imagen, niveles y colores sobre el mosaico entero (con --raw-only: mosaico en bruto)"),
    "assembler en mosaïque des images qui se recouvrent": ("assemble overlapping images into a mosaic", "montar en un mosaico imágenes que se solapan"),
    "un dossier, ou des images (jokers acceptés)": ("a folder, or images (wildcards accepted)", "una carpeta, o imágenes (se aceptan comodines)"),
    "fichier ou dossier de sortie (défaut : mosaique.tif dans le dossier des images)": (
        "output file or folder (default: mosaique.tif in the folder of the images)",
        "archivo o carpeta de salida (por defecto: mosaique.tif en la carpeta de las imágenes)"),
    "dans un dossier, assembler les empilements bruts (« _brut »)": (
        "in a folder, assemble the raw stacks (\"_brut\")",
        "en una carpeta, montar los apilados en bruto («_brut»)"),
    "appliquer les ondelettes et finitions d'un préréglage (images brutes) : ondelettes image par image, niveaux et couleurs sur la mosaïque entière": (
        "apply the wavelets and finishing of a preset (raw images): wavelets image by image, levels and colours on the whole mosaic",
        "aplicar las ondículas y el acabado de un preajuste (imágenes en bruto): ondículas imagen por imagen, niveles y colores sobre el mosaico entero"),
    "appliquer ondelettes et finitions à des images": ("apply wavelets and finishing to images", "aplicar ondículas y acabado a imágenes"),
    "lister ou importer des préréglages": ("list or import presets", "listar o importar preajustes"),
    "DOSSIER": ("FOLDER", "CARPETA"),
    "importer les réglages *-NOM.ini d'un dossier RegiStax 6": (
        "import the *-NAME.ini settings of a RegiStax 6 folder",
        "importar los ajustes *-NOMBRE.ini de una carpeta de RegiStax 6"),
    "créer une vidéo SER de démonstration": ("create a demo SER video", "crear un vídeo SER de demostración"),
    "écrire plutôt, dans le dossier indiqué, 9 champs lunaires qui se recouvrent, pour essayer la mosaïque": (
        "write instead, in the folder given, 9 overlapping lunar fields to try the mosaic",
        "escribir en su lugar, en la carpeta indicada, 9 campos lunares que se solapan, para probar el mosaico"),
    "Interrompu.": ("Interrupted.", "Interrumpido."),

    # ------------------------------------------------------------------ alignment points report
    "Aucun point : l'image est trop petite pour la taille des boîtes, le rayon de recherche et la marge au bord choisis.": (
        "No point: the image is too small for the box size, search radius and edge margin chosen.",
        "Ningún punto: la imagen es demasiado pequeña para el tamaño de las cajas, el radio de búsqueda y el margen elegidos."),
    "{n} point(s) d'alignement.": ("{n} alignment point(s).", "{n} punto(s) de alineación."),
    "{n} zones plus claires que {limit}": ("{n} areas brighter than {limit}", "{n} zonas más claras que {limit}"),
    "{n} zones plus sombres que {limit}": ("{n} areas darker than {limit}", "{n} zonas más oscuras que {limit}"),
    "{n} zones sans assez de détail": ("{n} areas without enough detail", "{n} zonas sin suficiente detalle"),
    "{n} au-delà du maximum de {limit}": ("{n} beyond the maximum of {limit}", "{n} por encima del máximo de {limit}"),
    "Écartées : {list}.": ("Left out: {list}.", "Descartadas: {list}."),
    "Luminosité des zones : {lo} à {hi} sur 255 (médiane {median}).": (
        "Brightness of the areas: {lo} to {hi} out of 255 (median {median}).",
        "Brillo de las zonas: de {lo} a {hi} sobre 255 (mediana {median})."),
    "→ Montez « Luminosité max. » au-dessus de {value}.": (
        "→ Raise \"Max. brightness\" above {value}.", "→ Suba «Brillo máx.» por encima de {value}."),
    "→ Descendez « Luminosité min. » sous {value}.": (
        "→ Lower \"Min. brightness\" below {value}.", "→ Baje «Brillo mín.» por debajo de {value}."),
    "→ Baissez « Détail minimal ».": ("→ Lower \"Minimum detail\".", "→ Baje «Detalle mínimo»."),

    # ------------------------------------------------------------------ mosaics
    "Placée": ("Placed", "Colocada"),
    "Même champ que {name}": ("Same field as {name}", "Mismo campo que {name}"),
    "Aucun recouvrement trouvé": ("No overlap found", "Ningún solapamiento encontrado"),
    "Il faut au moins deux images pour une mosaïque.": ("A mosaic needs at least two images.", "Un mosaico necesita al menos dos imágenes."),
    "Aucune mosaïque : aucune image ne recouvre une autre.": (
        "No mosaic: no image overlaps another one.", "Ningún mosaico: ninguna imagen se solapa con otra."),
    "Mosaïque {n}": ("Mosaic {n}", "Mosaico {n}"),
    "Mosaïque": ("Mosaic", "Mosaico"),
    "{title} : {n} images, {width} × {height} px, écart moyen aux raccords {rms} px, luminosité et couleurs égalisées (corrections jusqu'à {spread} %).": (
        "{title}: {n} images, {width} × {height} px, mean mismatch at the seams {rms} px, "
        "brightness and colours evened out (corrections up to {spread} %).",
        "{title}: {n} imágenes, {width} × {height} px, desajuste medio en las uniones {rms} px, "
        "brillo y colores igualados (correcciones de hasta un {spread} %)."),
    "Laissées de côté, sans recouvrement trouvé : {names}. Il faut environ 25 % de recouvrement entre voisines et assez de détails (un ciel uni ou une mer lisse ne suffisent pas).": (
        "Left aside, no overlap found: {names}. Neighbours need about 25 % of overlap and enough "
        "detail (a plain sky or a smooth sea are not enough).",
        "Dejadas de lado, sin solapamiento: {names}. Las vecinas necesitan un 25 % de solapamiento "
        "aproximadamente y suficiente detalle (un cielo liso o un mar en calma no bastan)."),
    "Laissées de côté car elles montrent le même champ qu'une autre : {list}.": (
        "Left aside as they show the same field as another one: {list}.",
        "Dejadas de lado porque muestran el mismo campo que otra: {list}."),
    "{name} (comme {other})": ("{name} (like {other})", "{name} (como {other})"),
    "{name} : {reason}.": ("{name}: {reason}.", "{name}: {reason}."),
    "mémoire insuffisante pour la lire": ("not enough memory to read it", "memoria insuficiente para leerla"),
    "illisible ({error})": ("unreadable ({error})", "ilegible ({error})"),
    "Recherche des détails : image {done}/{total}": ("Looking for details: image {done}/{total}", "Búsqueda de detalles: imagen {done}/{total}"),
    "image vide": ("empty image", "imagen vacía"),
    "bien plus grande que les autres (déjà une mosaïque ?)": (
        "much larger than the others (a mosaic already?)", "mucho más grande que las demás (¿ya un mosaico?)"),
    "Recherche des recouvrements : {n} trouvés": ("Looking for overlaps: {n} found", "Búsqueda de solapamientos: {n} encontrados"),
    "Placement des images": ("Placing the images", "Colocación de las imágenes"),
    "placement incohérent (mosaïque de {width} × {height} px)": (
        "inconsistent placement (mosaic of {width} × {height} px)", "colocación incoherente (mosaico de {width} × {height} px)"),
    "Placement terminé": ("Placement done", "Colocación terminada"),
    "Assemblage : {percent} %": ("Assembling: {percent} %", "Montaje: {percent} %"),

    # ------------------------------------------------------------------ processing
    "{label} : {done}/{total}": ("{label}: {done}/{total}", "{label}: {done}/{total}"),
    "Analyse de la qualité": ("Quality analysis", "Análisis de la calidad"),
    "Image de référence : {done}/{total}": ("Reference image: {done}/{total}", "Imagen de referencia: {done}/{total}"),
    "Alignement": ("Alignment", "Alineación"),
    "Empilement": ("Stacking", "Apilado"),
    "Aucune image n'a été empilée": ("No frame was stacked", "No se ha apilado ninguna imagen"),

    # ------------------------------------------------------------------ batch window
    "il faut au moins deux images": ("at least two images are needed", "se necesitan al menos dos imágenes"),
    "mémoire insuffisante": ("not enough memory", "memoria insuficiente"),
    "Traitement par lot": ("Batch processing", "Procesamiento por lotes"),
    "Vidéos à traiter :": ("Videos to process:", "Vídeos que procesar:"),
    "Dossier des vidéos": ("Folder of the videos", "Carpeta de los vídeos"),
    "Images produites :": ("Images produced:", "Imágenes producidas:"),
    "Dossier des images": ("Folder of the images", "Carpeta de las imágenes"),
    "Réglages actuels de la fenêtre principale": ("Current settings of the main window", "Ajustes actuales de la ventana principal"),
    "Préréglage « {name} »": ("Preset \"{name}\"", "Preajuste «{name}»"),
    "Réglages :": ("Settings:", "Ajustes:"),
    "Format :": ("Format:", "Formato:"),
    "Image traitée (ondelettes et finitions)": ("Processed image (wavelets and finishing)", "Imagen procesada (ondículas y acabado)"),
    "Empilement brut (suffixe « _brut »)": ("Raw stack (suffix \"_brut\")", "Apilado en bruto (sufijo «_brut»)"),
    "Alignement RVB automatique pour chaque vidéo couleur": (
        "Automatic RGB alignment for each colour video", "Alineación RGB automática para cada vídeo en color"),
    "Ignorer les vidéos déjà traitées": ("Skip the videos already processed", "Omitir los vídeos ya procesados"),
    "Assembler les images en une mosaïque (Lune, Soleil, paysage…)": (
        "Assemble the images into a mosaic (Moon, Sun, landscape…)",
        "Montar las imágenes en un mosaico (Luna, Sol, paisaje…)"),
    "À la fin du lot, les images qui se recouvrent sont assemblées dans « mosaique.tif ».\nLa mosaïque part des empilements bruts (enregistrés aussi) : les ondelettes sont appliquées\nimage par image, mais les niveaux et les couleurs une seule fois, à la mosaïque entière,\naprès égalisation : un ciel n'est pas brûlé dans une image et pas dans sa voisine.": (
        "At the end of the batch, the overlapping images are assembled into \"mosaique.tif\".\n"
        "The mosaic starts from the raw stacks (saved as well): wavelets are applied image by\n"
        "image, but levels and colours only once, to the whole mosaic, after evening out: a sky\n"
        "is not burnt out in one image and not in its neighbour.",
        "Al final del lote, las imágenes que se solapan se montan en «mosaique.tif».\n"
        "El mosaico parte de los apilados en bruto (guardados también): las ondículas se aplican\n"
        "imagen por imagen, pero los niveles y los colores una sola vez, al mosaico entero, tras\n"
        "igualarlo: un cielo no queda quemado en una imagen y no en su vecina."),
    "Enregistrer :": ("Save:", "Guardar:"),
    "Vidéo": ("Video", "Vídeo"),
    "Taille": ("Size", "Tamaño"),
    "État": ("State", "Estado"),
    "Démarrer": ("Start", "Iniciar"),
    "Annuler": ("Cancel", "Cancelar"),
    "Actualiser": ("Refresh", "Actualizar"),
    "Ouvrir le dossier des images": ("Open the folder of the images", "Abrir la carpeta de las imágenes"),
    "Fermer": ("Close", "Cerrar"),
    "Parcourir…": ("Browse…", "Examinar…"),
    "Ouvrir": ("Open", "Abrir"),
    "Nécessaire à la mosaïque": ("Needed by the mosaic", "Necesario para el mosaico"),
    "Déjà traitée": ("Already processed", "Ya procesado"),
    "À traiter": ("To process", "Por procesar"),
    "Le dossier des vidéos n'existe pas.": ("The folder of the videos does not exist.", "La carpeta de los vídeos no existe."),
    "Aucune vidéo (SER, AVI…) dans ce dossier : déposez-y vos captures.": (
        "No video (SER, AVI…) in this folder: put your captures in it.",
        "Ningún vídeo (SER, AVI…) en esta carpeta: deje en ella sus capturas."),
    "{videos} vidéo(s), dont {todo} à traiter.": ("{videos} video(s), {todo} of them to process.", "{videos} vídeo(s), {todo} por procesar."),
    " Puis assemblage de la mosaïque.": (" Then assembly of the mosaic.", " Después, montaje del mosaico."),
    "Préréglage illisible :\n{error}": ("Unreadable preset:\n{error}", "Preajuste ilegible:\n{error}"),
    "Dossier des images inutilisable :\n{error}": ("Unusable folder for the images:\n{error}", "Carpeta de las imágenes inutilizable:\n{error}"),
    "En attente": ("Waiting", "En espera"),
    "En cours…": ("In progress…", "En curso…"),
    "Vidéo {index} / {videos}": ("Video {index} / {videos}", "Vídeo {index} / {videos}"),
    "Mosaïque : {summary}": ("Mosaic: {summary}", "Mosaico: {summary}"),
    "Enregistrée : {path}": ("Saved: {path}", "Guardado: {path}"),
    "Mosaïque impossible : {error}": ("Mosaic impossible: {error}", "Mosaico imposible: {error}"),
    "En cours… {percent} %": ("In progress… {percent} %", "En curso… {percent} %"),
    "✓ {stacked}/{frames} images, {points} points, {seconds} s → {names}": (
        "✓ {stacked}/{frames} frames, {points} points, {seconds} s → {names}",
        "✓ {stacked}/{frames} imágenes, {points} puntos, {seconds} s → {names}"),
    "⚠ {stacked}/{frames} images, aucun point d'alignement (vérifiez Luminosité min./max.) → {names}": (
        "⚠ {stacked}/{frames} frames, no alignment point (check Min./Max. brightness) → {names}",
        "⚠ {stacked}/{frames} imágenes, ningún punto de alineación (revise Brillo mín./máx.) → {names}"),
    "✗ Erreur : {error}": ("✗ Error: {error}", "✗ Error: {error}"),
    "Terminé : {n} image(s) produite(s)": ("Done: {n} image(s) produced", "Terminado: {n} imagen(es) producida(s)"),
    ", {n} vidéo(s) en erreur": (", {n} video(s) failed", ", {n} vídeo(s) con error"),
    "Traitement annulé.": ("Processing cancelled.", "Procesamiento cancelado."),
    "Annulation…": ("Cancelling…", "Cancelando…"),
    "Un traitement est en cours. L'interrompre ?": ("A processing is running. Interrupt it?", "Hay un procesamiento en curso. ¿Interrumpirlo?"),

    # ------------------------------------------------------------------ main window: files, menus
    "Vidéos": ("Videos", "Vídeos"),
    "Images": ("Images", "Imágenes"),
    "Tous les fichiers (*)": ("All files (*)", "Todos los archivos (*)"),
    "TIFF 16 bits (*.tif)": ("16-bit TIFF (*.tif)", "TIFF de 16 bits (*.tif)"),
    "PNG 16 bits (*.png)": ("16-bit PNG (*.png)", "PNG de 16 bits (*.png)"),
    "FITS 32 bits flottant (*.fits)": ("32-bit float FITS (*.fits)", "FITS de 32 bits en coma flotante (*.fits)"),
    "FITS 16 bits (*.fit)": ("16-bit FITS (*.fit)", "FITS de 16 bits (*.fit)"),
    "Ordre chronologique": ("Chronological order", "Orden cronológico"),
    "Par qualité (meilleures d'abord)": ("By quality (best first)", "Por calidad (las mejores primero)"),
    "Image :": ("Frame:", "Imagen:"),
    "1 · Alignement": ("1 · Alignment", "1 · Alineación"),
    "2 · Sélection": ("2 · Selection", "2 · Selección"),
    "3 · Empilement": ("3 · Stacking", "3 · Apilado"),
    "4 · Ondelettes": ("4 · Wavelets", "4 · Ondículas"),
    "5 · Finitions": ("5 · Finishing", "5 · Acabado"),
    "Ouvrir une vidéo…": ("Open a video…", "Abrir un vídeo…"),
    "Ouvrir une vidéo SER/AVI ou une série d'images": ("Open a SER/AVI video or a series of images", "Abrir un vídeo SER/AVI o una serie de imágenes"),
    "Ouvrir une image à traiter…": ("Open an image to process…", "Abrir una imagen para procesar…"),
    "Ouvrir une image déjà empilée pour les ondelettes": ("Open an image already stacked, for the wavelets", "Abrir una imagen ya apilada, para las ondículas"),
    "Traitement par lot…": ("Batch processing…", "Procesamiento por lotes…"),
    "Traiter toutes les vidéos du dossier « input » : une image par vidéo dans « output »": (
        "Process every video of the \"input\" folder: one image per video in \"output\"",
        "Procesar todos los vídeos de la carpeta «input»: una imagen por vídeo en «output»"),
    "Assembler une mosaïque…": ("Assemble a mosaic…", "Montar un mosaico…"),
    "Assembler en une seule image des images qui se recouvrent (Lune, Soleil, paysage)": (
        "Assemble overlapping images into a single one (Moon, Sun, landscape)",
        "Montar en una sola imagen varias imágenes que se solapan (Luna, Sol, paisaje)"),
    "Enregistrer l'image…": ("Save the image…", "Guardar la imagen…"),
    "Enregistrer le résultat (ondelettes et finitions comprises)": (
        "Save the result (wavelets and finishing included)", "Guardar el resultado (ondículas y acabado incluidos)"),
    "Enregistrer l'empilement brut…": ("Save the raw stack…", "Guardar el apilado en bruto…"),
    "Enregistrer l'empilement sans ondelettes ni finitions": (
        "Save the stack without wavelets nor finishing", "Guardar el apilado sin ondículas ni acabado"),
    "▶  Tout faire": ("▶  Do all", "▶  Hacer todo"),
    "Analyse, alignement, sélection et empilement en une fois": (
        "Analysis, alignment, selection and stacking in one go", "Análisis, alineación, selección y apilado de una vez"),
    "Avant / après": ("Before / after", "Antes / después"),
    "Comparer avec l'empilement non traité": ("Compare with the unprocessed stack", "Comparar con el apilado sin procesar"),
    "Afficher les points": ("Show the points", "Mostrar los puntos"),
    "Ajuster à la fenêtre": ("Fit to window", "Ajustar a la ventana"),
    "Taille réelle (100 %)": ("Actual size (100 %)", "Tamaño real (100 %)"),
    "Zoom 200 %": ("Zoom 200 %", "Zoom 200 %"),
    "&Fichier": ("&File", "&Archivo"),
    "Quitter": ("Quit", "Salir"),
    "&Préréglages": ("&Presets", "&Preajustes"),
    "&Affichage": ("&View", "&Ver"),
    "Thème": ("Theme", "Tema"),
    "Sombre": ("Dark", "Oscuro"),
    "Clair": ("Light", "Claro"),
    "Nuit (rouge, préserve la vision nocturne)": ("Night (red, keeps night vision)", "Noche (rojo, preserva la visión nocturna)"),
    "Langue": ("Language", "Idioma"),
    "Automatique (langue du système)": ("Automatic (language of the system)", "Automático (idioma del sistema)"),
    "&Aide": ("&Help", "A&yuda"),
    "Créer un raccourci sur le Bureau": ("Create a shortcut on the Desktop", "Crear un acceso directo en el Escritorio"),
    "À propos de PlanStax": ("About PlanStax", "Acerca de PlanStax"),
    "Outils": ("Tools", "Herramientas"),
    "Ouvrez une vidéo ({key}+O) ou glissez-la dans la fenêtre.": (
        "Open a video ({key}+O) or drop it in the window.", "Abra un vídeo ({key}+O) o arrástrelo a la ventana."),

    # ------------------------------------------------------------------ tab 1: alignment
    "Source": ("Source", "Fuente"),
    "Aucune vidéo ouverte": ("No video open", "Ningún vídeo abierto"),
    "Automatique (selon le fichier)": ("Automatic (from the file)", "Automática (según el archivo)"),
    "Aucune (mono)": ("None (mono)", "Ninguna (mono)"),
    "Matrice de Bayer :": ("Bayer matrix:", "Matriz de Bayer:"),
    "Objet": ("Object", "Objeto"),
    "Automatique": ("Automatic", "Automático"),
    "Planète (disque sur fond noir)": ("Planet (disc on a black background)", "Planeta (disco sobre fondo negro)"),
    "Surface (Lune, Soleil)": ("Surface (Moon, Sun)", "Superficie (Luna, Sol)"),
    "Type :": ("Type:", "Tipo:"),
    "Lissage appliqué avant la mesure de netteté : augmentez-le pour des vidéos bruitées afin que le bruit ne passe pas pour du détail.": (
        "Smoothing applied before measuring sharpness: increase it for noisy videos so that noise is not taken for detail.",
        "Suavizado aplicado antes de medir la nitidez: auméntelo en vídeos con ruido para que el ruido no pase por detalle."),
    "Robustesse au bruit :": ("Noise robustness:", "Robustez al ruido:"),
    "Nombre de meilleures images moyennées pour la référence (auto = 10 %, 3 à 50)": (
        "Number of best frames averaged into the reference (auto = 10 %, 3 to 50)",
        "Número de mejores imágenes promediadas para la referencia (auto = 10 %, de 3 a 50)"),
    "Images de référence :": ("Reference frames:", "Imágenes de referencia:"),
    "Points d'alignement": ("Alignment points", "Puntos de alineación"),
    "Espacement :": ("Spacing:", "Espaciado:"),
    "Taille des boîtes :": ("Box size:", "Tamaño de las cajas:"),
    "Déplacement local maximal recherché autour de chaque point": (
        "Largest local displacement searched around each point", "Desplazamiento local máximo buscado alrededor de cada punto"),
    "Rayon de recherche :": ("Search radius:", "Radio de búsqueda:"),
    "Luminosité min. :": ("Min. brightness:", "Brillo mín.:"),
    "Luminosité max. :": ("Max. brightness:", "Brillo máx.:"),
    "Marge au bord :": ("Edge margin:", "Margen del borde:"),
    "Nombre maximal :": ("Maximum number:", "Número máximo:"),
    "Écarte les zones sans détail (moins de x % du détail de la meilleure zone)": (
        "Leaves out areas without detail (less than x % of the detail of the best area)",
        "Descarta las zonas sin detalle (menos del x % del detalle de la mejor zona)"),
    "Détail minimal :": ("Minimum detail:", "Detalle mínimo:"),
    "Placer les points": ("Place the points", "Colocar los puntos"),
    "{key} + clic sur l'image : ajouter un point · Maj + clic : supprimer · molette : zoom · glisser : déplacer": (
        "{key} + click on the image: add a point · Shift + click: remove · wheel: zoom · drag: move",
        "{key} + clic en la imagen: añadir un punto · Mayús + clic: quitar · rueda: zoom · arrastrar: mover"),
    "Aligner": ("Align", "Alinear"),

    # ------------------------------------------------------------------ tab 2: selection
    "Garder les meilleures images": ("Keep the best frames", "Conservar las mejores imágenes"),
    "Pourcentage": ("Percentage", "Porcentaje"),
    "Nombre d'images": ("Number of frames", "Número de imágenes"),
    "Qualité minimale": ("Minimum quality", "Calidad mínima"),
    "Méthode :": ("Method:", "Método:"),
    "Pourcentage :": ("Percentage:", "Porcentaje:"),
    "Nombre :": ("Number:", "Número:"),
    "En pourcentage de la qualité de la meilleure image": ("As a percentage of the quality of the best frame", "En porcentaje de la calidad de la mejor imagen"),
    "Qualité minimale :": ("Minimum quality:", "Calidad mínima:"),
    "Qualité des images": ("Quality of the frames", "Calidad de las imágenes"),
    "La barre sous l'image permet de parcourir la vidéo, dans l'ordre chronologique ou de la meilleure à la pire image.": (
        "The bar under the image browses the video, in chronological order or from the best to the worst frame.",
        "La barra bajo la imagen permite recorrer el vídeo, en orden cronológico o de la mejor a la peor imagen."),

    # ------------------------------------------------------------------ tab 3: stacking
    "Pour chaque point d'alignement, ne garder que ce pourcentage des images retenues, les plus nettes à cet endroit précis (100 % = mêmes images partout, comme RegiStax).": (
        "For each alignment point, only keep this percentage of the selected frames, the sharpest at "
        "that very place (100 % = the same frames everywhere, as RegiStax).",
        "Para cada punto de alineación, conservar solo este porcentaje de las imágenes seleccionadas, las "
        "más nítidas en ese lugar preciso (100 % = las mismas imágenes en todas partes, como RegiStax)."),
    "Sélection locale :": ("Local selection:", "Selección local:"),
    "1× (taille d'origine)": ("1× (original size)", "1× (tamaño original)"),
    "Agrandissement pendant l'empilement (type « drizzle »)": (
        "Enlargement during stacking (\"drizzle\" kind)", "Ampliación durante el apilado (tipo «drizzle»)"),
    "Agrandissement :": ("Enlargement:", "Ampliación:"),
    "Égaliser la luminosité des images": ("Even out the brightness of the frames", "Igualar el brillo de las imágenes"),
    "Compense les variations de transparence (voiles, brume)": (
        "Makes up for changes of transparency (veils, haze)", "Compensa las variaciones de transparencia (velos, bruma)"),
    "Pondérer par la qualité": ("Weight by quality", "Ponderar por la calidad"),
    "Empiler": ("Stack", "Apilar"),

    # ------------------------------------------------------------------ tab 4: wavelets
    "Méthode": ("Method", "Método"),
    "B3-spline « à trous » (linéaire)": ("B3-spline \"à trous\" (linear)", "B3-spline «à trous» (lineal)"),
    "Gaussienne": ("Gaussian", "Gaussiana"),
    "Schéma :": ("Scheme:", "Esquema:"),
    "Dyadique (1, 2, 4, 8…)": ("Dyadic (1, 2, 4, 8…)", "Diádica (1, 2, 4, 8…)"),
    "Linéaire (1, 2, 3, 4…)": ("Linear (1, 2, 3, 4…)", "Lineal (1, 2, 3, 4…)"),
    "Progression :": ("Progression:", "Progresión:"),
    "Taille de la 1ʳᵉ couche :": ("Size of the 1st layer:", "Tamaño de la 1.ª capa:"),
    "Canaux RVB": ("RGB channels", "Canales RGB"),
    "Luminance seulement": ("Luminance only", "Solo luminancia"),
    "En luminance, l'accentuation n'amplifie pas le bruit de couleur": (
        "On luminance, sharpening does not amplify colour noise", "En luminancia, el realce no amplifica el ruido de color"),
    "Appliquer sur :": ("Apply to:", "Aplicar a:"),
    "Couches": ("Layers", "Capas"),
    "Accentuation": ("Sharpening", "Realce"),
    "Gain": ("Gain", "Ganancia"),
    "Débruitage": ("Denoising", "Reducción de ruido"),
    "Couche {n}": ("Layer {n}", "Capa {n}"),
    "Accentuation de cette couche : 0 = image intacte, 100 = le plus fort.\nLa plage est adaptée à chaque couche : un même réglage donne un effet\ncomparable de la couche 1 à la couche 6.": (
        "Sharpening of this layer: 0 = image untouched, 100 = strongest.\n"
        "The range suits each layer: the same setting gives a comparable effect\n"
        "from layer 1 to layer 6.",
        "Realce de esta capa: 0 = imagen intacta, 100 = el más fuerte.\n"
        "El intervalo se adapta a cada capa: un mismo ajuste da un efecto\n"
        "comparable de la capa 1 a la capa 6."),
    "Gain appliqué à la couche (valeur enregistrée dans les préréglages)": (
        "Gain applied to the layer (the value saved in the presets)", "Ganancia aplicada a la capa (valor guardado en los preajustes)"),
    "Débruitage de la couche (0 = aucun)": ("Denoising of the layer (0 = none)", "Reducción de ruido de la capa (0 = ninguna)"),
    "Réinitialiser les couches": ("Reset the layers", "Restablecer las capas"),
    "Accentuation de 0 (image intacte) à 100. Couches 1-2 : détails fins (et bruit). Couches 3-4 : structures moyennes. Couches 5-6 : grandes structures. Commencez vers 30 à 50 sur les couches 1 à 3.": (
        "Sharpening from 0 (image untouched) to 100. Layers 1-2: fine detail (and noise). Layers 3-4: "
        "medium structures. Layers 5-6: large structures. Start around 30 to 50 on layers 1 to 3.",
        "Realce de 0 (imagen intacta) a 100. Capas 1-2: detalles finos (y ruido). Capas 3-4: estructuras "
        "medias. Capas 5-6: grandes estructuras. Empiece hacia 30 a 50 en las capas 1 a 3."),

    # ------------------------------------------------------------------ tab 5: finishing
    "Alignement des couleurs (dispersion atmosphérique)": (
        "Colour alignment (atmospheric dispersion)", "Alineación de los colores (dispersión atmosférica)"),
    "Alignement RVB automatique": ("Automatic RGB alignment", "Alineación RGB automática"),
    "Rouge": ("Red", "Rojo"),
    "Bleu": ("Blue", "Azul"),
    "{label} :": ("{label}:", "{label}:"),
    "Balance des couleurs": ("Colour balance", "Balance de color"),
    "Balance automatique": ("Automatic balance", "Balance automático"),
    "Vert": ("Green", "Verde"),
    "Saturation :": ("Saturation:", "Saturación:"),
    "Niveaux": ("Levels", "Niveles"),
    "Point noir": ("Black point", "Punto negro"),
    "Point blanc": ("White point", "Punto blanco"),
    "Gamma": ("Gamma", "Gamma"),
    "Luminosité": ("Brightness", "Brillo"),
    "Contraste": ("Contrast", "Contraste"),
    "Étirement automatique": ("Automatic stretch", "Estiramiento automático"),
    "Orientation": ("Orientation", "Orientación"),
    "90° horaire": ("90° clockwise", "90° en sentido horario"),
    "90° antihoraire": ("90° anticlockwise", "90° en sentido antihorario"),
    "Rotation :": ("Rotation:", "Rotación:"),
    "Rotation fine de l'image finale, en degrés (positif : sens horaire).\nL'image est agrandie pour que rien ne soit coupé : les coins sont noirs.": (
        "Fine rotation of the final image, in degrees (positive: clockwise).\n"
        "The image is enlarged so that nothing is cut off: the corners are black.",
        "Rotación fina de la imagen final, en grados (positivo: sentido horario).\n"
        "La imagen se amplía para que no se corte nada: las esquinas quedan negras."),
    "Rotation fine :": ("Fine rotation:", "Rotación fina:"),
    "Miroir horizontal": ("Horizontal mirror", "Espejo horizontal"),
    "Miroir vertical": ("Vertical mirror", "Espejo vertical"),
    "Réinitialiser les finitions": ("Reset the finishing", "Restablecer el acabado"),

    # ------------------------------------------------------------------ main window: files and processing
    "Ouvrir une vidéo ou une série d'images": ("Open a video or a series of images", "Abrir un vídeo o una serie de imágenes"),
    "Ouvrir une image à traiter": ("Open an image to process", "Abrir una imagen para procesar"),
    "Impossible d'ouvrir le fichier :\n{error}": ("Cannot open the file:\n{error}", "No se puede abrir el archivo:\n{error}"),
    "{source} — cliquez sur « Tout faire » (F5) ou procédez étape par étape.": (
        "{source} — click \"Do all\" (F5) or proceed step by step.", "{source} — pulse «Hacer todo» (F5) o proceda paso a paso."),
    "Impossible d'ouvrir l'image :\n{error}": ("Cannot open the image:\n{error}", "No se puede abrir la imagen:\n{error}"),
    "Image seule (pas de vidéo)": ("Single image (no video)", "Imagen sola (sin vídeo)"),
    "Enregistrement impossible :\n{error}": ("Cannot save:\n{error}", "No se puede guardar:\n{error}"),
    "Enregistré : {path}": ("Saved: {path}", "Guardado: {path}"),
    "Enregistrer l'image traitée": ("Save the processed image", "Guardar la imagen procesada"),
    "Enregistrer l'empilement brut": ("Save the raw stack", "Guardar el apilado en bruto"),
    "Erreur pendant le traitement.": ("Error during processing.", "Error durante el procesamiento."),
    "Analyse de la vidéo…": ("Analysing the video…", "Analizando el vídeo…"),
    "{n} points d'alignement placés. Ajustez-les si besoin puis cliquez sur « Aligner ».": (
        "{n} alignment points placed. Adjust them if needed, then click \"Align\".",
        "{n} puntos de alineación colocados. Ajústelos si es necesario y pulse «Alinear»."),
    "Aucun point d'alignement placé : l'explication est dans l'onglet Alignement.": (
        "No alignment point placed: the explanation is in the Alignment tab.",
        "Ningún punto de alineación colocado: la explicación está en la pestaña Alineación."),
    "Alignement…": ("Aligning…", "Alineando…"),
    "Alignement terminé : {frames} images, {points} points, {valid} % des mesures locales fiables.": (
        "Alignment done: {frames} frames, {points} points, {valid} % of the local measurements reliable.",
        "Alineación terminada: {frames} imágenes, {points} puntos, {valid} % de las medidas locales fiables."),
    "Alignement terminé. Vérifiez la sélection puis empilez.": (
        "Alignment done. Check the selection, then stack.", "Alineación terminada. Revise la selección y apile."),
    "Empilement…": ("Stacking…", "Apilando…"),
    "Traitement complet…": ("Full processing…", "Procesamiento completo…"),
    "{stacked} images empilées sur {frames}, {points} points d'alignement, {width}×{height} px.": (
        "{stacked} frames stacked out of {frames}, {points} alignment points, {width}×{height} px.",
        "{stacked} imágenes apiladas de {frames}, {points} puntos de alineación, {width}×{height} px."),
    "Empilement terminé. Réglez les ondelettes puis enregistrez ({key}+S).": (
        "Stacking done. Set the wavelets, then save ({key}+S).", "Apilado terminado. Ajuste las ondículas y guarde ({key}+S)."),
    "Paramètres modifiés : cliquez sur « Placer les points ».": (
        "Settings changed: click \"Place the points\".", "Parámetros modificados: pulse «Colocar los puntos»."),
    "Trop près du bord pour placer un point ici.": ("Too close to the edge to place a point here.", "Demasiado cerca del borde para colocar un punto aquí."),
    "{kept} images retenues sur {frames} ({percent} %)": ("{kept} frames kept out of {frames} ({percent} %)", "{kept} imágenes conservadas de {frames} ({percent} %)"),
    "Lecture impossible : {error}": ("Cannot read: {error}", "No se puede leer: {error}"),
    "n° {index}/{frames}": ("no. {index}/{frames}", "n.º {index}/{frames}"),
    " · rang {rank} · qualité {quality} %": (" · rank {rank} · quality {quality} %", " · puesto {rank} · calidad {quality} %"),
    " · retenue": (" · kept", " · conservada"),
    " · écartée": (" · left out", " · descartada"),
    "Décalages mesurés — rouge : ({rx}, {ry}) px, bleu : ({bx}, {by}) px": (
        "Shifts measured — red: ({rx}, {ry}) px, blue: ({bx}, {by}) px",
        "Desplazamientos medidos — rojo: ({rx}, {ry}) px, azul: ({bx}, {by}) px"),

    # ------------------------------------------------------------------ presets, help
    "(aucun préréglage)": ("(no preset)", "(ningún preajuste)"),
    "Enregistrer les réglages actuels…": ("Save the current settings…", "Guardar los ajustes actuales…"),
    "Importer depuis RegiStax 6…": ("Import from RegiStax 6…", "Importar desde RegiStax 6…"),
    "Réglages par défaut": ("Default settings", "Ajustes por defecto"),
    "Ouvrir le dossier des préréglages": ("Open the presets folder", "Abrir la carpeta de los preajustes"),
    "Préréglage « {name} » chargé.": ("Preset \"{name}\" loaded.", "Preajuste «{name}» cargado."),
    "Enregistrer un préréglage": ("Save a preset", "Guardar un preajuste"),
    "Nom du préréglage :": ("Name of the preset:", "Nombre del preajuste:"),
    "Préréglage « {name} » enregistré.": ("Preset \"{name}\" saved.", "Preajuste «{name}» guardado."),
    "Dossier de RegiStax 6": ("RegiStax 6 folder", "Carpeta de RegiStax 6"),
    "Préréglages importés : {names}.\n\nPoints d'alignement, sélection et type d'ondelettes sont repris tels quels. Les curseurs d'ondelettes, eux, ne peuvent pas être convertis (la formule de RegiStax n'est pas publique) : ils sont laissés au neutre, à régler à l'œil.\n\nPositions RegiStax d'origine (couches 1 à 6, 10 = neutre) :\n": (
        "Presets imported: {names}.\n\nAlignment points, selection and kind of wavelets are taken as they are. "
        "The wavelet sliders, however, cannot be converted (the RegiStax formula is not public): they are "
        "left neutral, to be set by eye.\n\nOriginal RegiStax positions (layers 1 to 6, 10 = neutral):\n",
        "Preajustes importados: {names}.\n\nLos puntos de alineación, la selección y el tipo de ondículas se "
        "conservan tal cual. Los cursores de ondículas, en cambio, no se pueden convertir (la fórmula de "
        "RegiStax no es pública): quedan en neutro, para ajustarlos a ojo.\n\nPosiciones originales de "
        "RegiStax (capas 1 a 6, 10 = neutro):\n"),
    "Aucun fichier de réglages RegiStax (estimate-*.ini, wavelet-*.ini…) trouvé dans ce dossier.": (
        "No RegiStax settings file (estimate-*.ini, wavelet-*.ini…) found in this folder.",
        "Ningún archivo de ajustes de RegiStax (estimate-*.ini, wavelet-*.ini…) en esta carpeta."),
    "Redémarrez PlanStax pour changer de langue.": ("Restart PlanStax to change the language.", "Reinicie PlanStax para cambiar de idioma."),
    "Guide rapide": ("Quick guide", "Guía rápida"),
    "1. Ouvrez une vidéo SER ou AVI ({key}+O, ou glisser-déposer).\n2. Cliquez sur « Tout faire » (F5) : analyse de la qualité, image de référence, points d'alignement, alignement, sélection et empilement.\n3. Onglet Ondelettes : montez l'accentuation des couches 1 à 3 (30 à 50 pour commencer), et utilisez le débruitage des couches 1-2 si le bruit apparaît.\n4. Onglet Finitions : alignement RVB automatique, balance des couleurs, niveaux, orientation.\n5. Enregistrez ({key}+S) en TIFF 16 bits.\n\nPlusieurs vidéos : déposez-les dans le dossier « input », puis Fichier → Traitement par lot ({key}+L). Une image par vidéo est écrite dans le dossier « output ».\n\nMosaïque (Lune, Soleil, paysage pris en plusieurs champs) : cochez « Assembler les images en une mosaïque » dans le traitement par lot, ou Fichier → Assembler une mosaïque ({mosaic_key}). Prévoyez environ 25 % de recouvrement entre champs voisins.\n\nPour affiner : réglez les points dans l'onglet Alignement ({key}+clic pour en ajouter, Maj+clic pour en retirer), le pourcentage d'images gardées dans l'onglet Sélection, et la sélection locale dans l'onglet Empilement.\n\nTouche B : avant/après · F : ajuster · 1 : 100 % · P : afficher les points.": (
        "1. Open a SER or AVI video ({key}+O, or drag and drop).\n"
        "2. Click \"Do all\" (F5): quality analysis, reference image, alignment points, alignment, "
        "selection and stacking.\n"
        "3. Wavelets tab: raise the sharpening of layers 1 to 3 (30 to 50 to begin with), and use the "
        "denoising of layers 1-2 if noise shows.\n"
        "4. Finishing tab: automatic RGB alignment, colour balance, levels, orientation.\n"
        "5. Save ({key}+S) as 16-bit TIFF.\n\n"
        "Several videos: put them in the \"input\" folder, then File → Batch processing ({key}+L). One "
        "image per video is written to the \"output\" folder.\n\n"
        "Mosaic (Moon, Sun, landscape shot in several fields): tick \"Assemble the images into a mosaic\" "
        "in the batch processing, or File → Assemble a mosaic ({mosaic_key}). Plan about 25 % of overlap "
        "between neighbouring fields.\n\n"
        "To refine: set the points in the Alignment tab ({key}+click to add some, Shift+click to remove "
        "them), the percentage of frames kept in the Selection tab, and the local selection in the "
        "Stacking tab.\n\n"
        "Key B: before/after · F: fit · 1: 100 % · P: show the points.",
        "1. Abra un vídeo SER o AVI ({key}+O, o arrastrar y soltar).\n"
        "2. Pulse «Hacer todo» (F5): análisis de la calidad, imagen de referencia, puntos de alineación, "
        "alineación, selección y apilado.\n"
        "3. Pestaña Ondículas: suba el realce de las capas 1 a 3 (de 30 a 50 para empezar) y use la "
        "reducción de ruido de las capas 1-2 si aparece ruido.\n"
        "4. Pestaña Acabado: alineación RGB automática, balance de color, niveles, orientación.\n"
        "5. Guarde ({key}+S) en TIFF de 16 bits.\n\n"
        "Varios vídeos: déjelos en la carpeta «input» y luego Archivo → Procesamiento por lotes ({key}+L). "
        "Se escribe una imagen por vídeo en la carpeta «output».\n\n"
        "Mosaico (Luna, Sol, paisaje tomado en varios campos): marque «Montar las imágenes en un mosaico» "
        "en el procesamiento por lotes, o Archivo → Montar un mosaico ({mosaic_key}). Prevea un 25 % de "
        "solapamiento aproximadamente entre campos vecinos.\n\n"
        "Para afinar: ajuste los puntos en la pestaña Alineación ({key}+clic para añadir, Mayús+clic para "
        "quitar), el porcentaje de imágenes conservadas en la pestaña Selección y la selección local en la "
        "pestaña Apilado.\n\n"
        "Tecla B: antes/después · F: ajustar · 1: 100 % · P: mostrar los puntos."),
    "Impossible de créer le raccourci :\n{error}": ("Cannot create the shortcut:\n{error}", "No se puede crear el acceso directo:\n{error}"),
    "Raccourci créé sur le Bureau :\n{path}": ("Shortcut created on the Desktop:\n{path}", "Acceso directo creado en el Escritorio:\n{path}"),
    "À propos de {app}": ("About {app}", "Acerca de {app}"),
    "Empilement « lucky imaging » et ondelettes pour l'imagerie planétaire.<br><br>Programme indépendant écrit de zéro, inspiré du déroulement de travail de RegiStax 6 (sans lien avec RegiStax ni son auteur) : alignement multipoints, sélection des meilleures images, empilement local, ondelettes à 6 couches, mosaïques.<br><br>Formats : SER, AVI, MP4, FITS, TIFF, PNG, JPEG.<br>Interface : français, anglais, espagnol.": (
        "Lucky-imaging stacking and wavelets for planetary imaging.<br><br>Independent program written "
        "from scratch, inspired by the RegiStax 6 workflow (with no link to RegiStax nor its author): "
        "multi-point alignment, selection of the best frames, local stacking, 6-layer wavelets, "
        "mosaics.<br><br>Formats: SER, AVI, MP4, FITS, TIFF, PNG, JPEG.<br>Interface: French, English, Spanish.",
        "Apilado «lucky imaging» y ondículas para la imagen planetaria.<br><br>Programa independiente escrito "
        "desde cero, inspirado en el flujo de trabajo de RegiStax 6 (sin relación con RegiStax ni con su "
        "autor): alineación multipunto, selección de las mejores imágenes, apilado local, ondículas de 6 "
        "capas, mosaicos.<br><br>Formatos: SER, AVI, MP4, FITS, TIFF, PNG, JPEG.<br>Interfaz: francés, "
        "inglés, español."),

    # ------------------------------------------------------------------ mosaic window
    "Assembler une mosaïque": ("Assemble a mosaic", "Montar un mosaico"),
    "Choisir des images…": ("Choose images…", "Elegir imágenes…"),
    "Empilements bruts (images « _brut ») plutôt que les images traitées": (
        "Raw stacks (\"_brut\" images) rather than the processed images",
        "Apilados en bruto (imágenes «_brut») en lugar de las imágenes procesadas"),
    "Aucun : assembler les images telles quelles": ("None: assemble the images as they are", "Ninguno: montar las imágenes tal cual"),
    "Ondelettes et finitions des réglages actuels": ("Wavelets and finishing of the current settings", "Ondículas y acabado de los ajustes actuales"),
    "Ondelettes et finitions du préréglage « {name} »": (
        "Wavelets and finishing of the preset \"{name}\"", "Ondículas y acabado del preajuste «{name}»"),
    "Pour des empilements bruts : les ondelettes sont appliquées à chaque image, les niveaux\net les couleurs une seule fois, à la mosaïque entière (un ciel brûlé dans une image et\npas dans sa voisine laisserait des zones visibles).": (
        "For raw stacks: the wavelets are applied to each image, the levels and colours\n"
        "only once, to the whole mosaic (a sky burnt out in one image and not in its\n"
        "neighbour would leave visible zones).",
        "Para apilados en bruto: las ondículas se aplican a cada imagen, los niveles y los\n"
        "colores una sola vez, al mosaico entero (un cielo quemado en una imagen y no en\n"
        "su vecina dejaría zonas visibles)."),
    "Images à assembler :": ("Images to assemble:", "Imágenes que montar:"),
    "Traitement :": ("Processing:", "Procesamiento:"),
    "Image": ("Image", "Imagen"),
    "L'aperçu de la mosaïque s'affichera ici.": ("The preview of the mosaic will show here.", "La vista previa del mosaico aparecerá aquí."),
    "Les images doivent se recouvrir d'environ 25 % et avoir été traitées avec les mêmes réglages. La mosaïque est enregistrée dans le dossier des images (mosaique.tif).": (
        "The images must overlap by about 25 % and have been processed with the same settings. "
        "The mosaic is saved in the folder of the images (mosaique.tif).",
        "Las imágenes deben solaparse un 25 % aproximadamente y haberse procesado con los mismos "
        "ajustes. El mosaico se guarda en la carpeta de las imágenes (mosaique.tif)."),
    "Assembler": ("Assemble", "Montar"),
    "Ouvrir dans PlanStax (ondelettes)": ("Open in PlanStax (wavelets)", "Abrir en PlanStax (ondículas)"),
    "Ouvrir le dossier": ("Open the folder", "Abrir la carpeta"),
    "Images à assembler": ("Images to assemble", "Imágenes que montar"),
    "Il faut au moins deux images qui se recouvrent.": ("At least two overlapping images are needed.", "Se necesitan al menos dos imágenes que se solapen."),
    "{n} images": ("{n} images", "{n} imágenes"),
    "Mosaïque de {mpx} Mpx : trop grande pour appliquer les ondelettes dans PlanStax (mémoire).": (
        "Mosaic of {mpx} Mpx: too large to apply the wavelets in PlanStax (memory).",
        "Mosaico de {mpx} Mpx: demasiado grande para aplicar las ondículas en PlanStax (memoria)."),
    "Choisissez plutôt un traitement dans la liste « Traitement » : les ondelettes seront appliquées image par image.": (
        "Choose a processing in the \"Processing\" list instead: the wavelets will be applied image by image.",
        "Elija mejor un procesamiento en la lista «Procesamiento»: las ondículas se aplicarán imagen por imagen."),
    "Terminé en {seconds} s": ("Done in {seconds} s", "Terminado en {seconds} s"),
    "Aucune mosaïque": ("No mosaic", "Ningún mosaico"),
    "Erreur": ("Error", "Error"),
    "Assemblage impossible :\n{error}": ("Cannot assemble:\n{error}", "Montaje imposible:\n{error}"),
    "Assemblage annulé": ("Assembly cancelled", "Montaje cancelado"),
    "Un assemblage est en cours. L'interrompre ?": ("An assembly is running. Interrupt it?", "Hay un montaje en curso. ¿Interrumpirlo?"),

    # ------------------------------------------------------------------ small widgets
    "PlanStax - empilement et ondelettes pour l'imagerie planétaire": (
        "PlanStax - stacking and wavelets for planetary imaging", "PlanStax - apilado y ondículas para la imagen planetaria"),
    "échec de la création du raccourci": ("the shortcut could not be created", "no se ha podido crear el acceso directo"),
    "Cliquez pour choisir combien d'images garder": ("Click to choose how many frames to keep", "Pulse para elegir cuántas imágenes conservar"),
    "Pas encore d'analyse": ("No analysis yet", "Todavía sin análisis"),
    "meilleure": ("best", "mejor"),
    "pire (n = {n})": ("worst (n = {n})", "peor (n = {n})"),
    "Mémoire insuffisante pour ce traitement.\nEssayez un agrandissement plus faible ou moins de points d'alignement.": (
        "Not enough memory for this processing.\nTry a smaller enlargement or fewer alignment points.",
        "Memoria insuficiente para este procesamiento.\nPruebe una ampliación menor o menos puntos de alineación."),
    "{n} Mo": ("{n} MB", "{n} MB"),
    "< 1 Mo": ("< 1 MB", "< 1 MB"),

    # ------------------------------------------------------------------ file reading
    "Fichier FITS tronqué": ("Truncated FITS file", "Archivo FITS truncado"),
    "Image FITS non prise en charge (NAXIS={naxis})": ("Unsupported FITS image (NAXIS={naxis})", "Imagen FITS no admitida (NAXIS={naxis})"),
    "Impossible de lire l'image : {path}": ("Cannot read the image: {path}", "No se puede leer la imagen: {path}"),
    "Format d'image non pris en charge : {ext}": ("Unsupported image format: {ext}", "Formato de imagen no admitido: {ext}"),
    "Fichier SER tronqué (en-tête incomplet)": ("Truncated SER file (incomplete header)", "Archivo SER truncado (cabecera incompleta)"),
    "Ce fichier n'est pas une vidéo SER valide": ("This file is not a valid SER video", "Este archivo no es un vídeo SER válido"),
    "Dimensions d'image invalides dans l'en-tête SER": ("Invalid image dimensions in the SER header", "Dimensiones de imagen no válidas en la cabecera SER"),
    "Le fichier SER ne contient aucune image": ("The SER file holds no frame", "El archivo SER no contiene ninguna imagen"),
    "Aucune image à écrire": ("No frame to write", "Ninguna imagen que escribir"),
    "Toutes les images doivent avoir la même taille": ("All frames must have the same size", "Todas las imágenes deben tener el mismo tamaño"),
    "Matrice de Bayer inconnue : {pattern}": ("Unknown Bayer matrix: {pattern}", "Matriz de Bayer desconocida: {pattern}"),
    "couleur": ("colour", "color"),
    "{name} — {frames} images, {width}×{height}, {bits} bits, {kind}": (
        "{name} — {frames} frames, {width}×{height}, {bits} bits, {kind}",
        "{name} — {frames} imágenes, {width}×{height}, {bits} bits, {kind}"),
    "Impossible d'ouvrir la vidéo : {path}": ("Cannot open the video: {path}", "No se puede abrir el vídeo: {path}"),
    "La vidéo ne contient aucune image lisible": ("The video holds no readable frame", "El vídeo no contiene ninguna imagen legible"),
    "Lecture impossible de l'image {index}": ("Cannot read frame {index}", "No se puede leer la imagen {index}"),
    "Aucune image sélectionnée": ("No image selected", "Ninguna imagen seleccionada"),
    "Taille différente pour {name}": ("Different size for {name}", "Tamaño distinto para {name}"),
    "Aucun fichier sélectionné": ("No file selected", "Ningún archivo seleccionado"),
    "Format non reconnu (attendu : SER, AVI ou une série d'images)": (
        "Unknown format (expected: SER, AVI or a series of images)",
        "Formato no reconocido (se esperaba: SER, AVI o una serie de imágenes)"),
}
