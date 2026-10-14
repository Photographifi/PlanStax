"""Minimal FITS (primary HDU image) reader and writer — enough for planetary frames and results."""

from __future__ import annotations

import numpy as np

BLOCK = 2880
CARD = 80

_BITPIX_DTYPES = {8: ">u1", 16: ">i2", 32: ">i4", 64: ">i8", -32: ">f4", -64: ">f8"}


def _card(key: str, value=None, comment: str = "") -> bytes:
    if value is None:
        text = key.ljust(CARD)
    else:
        if isinstance(value, bool):
            v = ("T" if value else "F").rjust(20)
        elif isinstance(value, (int, np.integer)):
            v = str(int(value)).rjust(20)
        elif isinstance(value, (float, np.floating)):
            v = repr(float(value)).upper().rjust(20)
        else:
            v = "'" + str(value).replace("'", "''").ljust(8) + "'"
        text = f"{key:<8}= {v}"
        if comment:
            text += f" / {comment}"
    return text[:CARD].ljust(CARD).encode("ascii", "replace")


def _parse_header(fh) -> dict:
    header: dict = {}
    while True:
        block = fh.read(BLOCK)
        if len(block) < BLOCK:
            raise ValueError("Fichier FITS tronqué")
        for i in range(0, BLOCK, CARD):
            card = block[i:i + CARD].decode("ascii", "replace")
            key = card[:8].strip()
            if key == "END":
                return header
            if card[8:10] != "= ":
                continue
            raw = card[10:]
            if raw.lstrip().startswith("'"):
                s = raw.lstrip()[1:]
                end = s.find("'")
                while end != -1 and s[end + 1:end + 2] == "'":
                    end = s.find("'", end + 2)
                value = s[:end].replace("''", "'").rstrip() if end != -1 else s.rstrip()
            else:
                token = raw.split("/", 1)[0].strip()
                if token in ("T", "F"):
                    value = token == "T"
                else:
                    try:
                        value = int(token)
                    except ValueError:
                        try:
                            value = float(token.replace("D", "E"))
                        except ValueError:
                            value = token
            header[key] = value


def read_fits(path: str) -> tuple[np.ndarray, dict]:
    """Return (data, header). Colour cubes (NAXIS3 == 3) come back as HxWx3."""
    with open(path, "rb") as fh:
        header = _parse_header(fh)
        bitpix = int(header["BITPIX"])
        naxis = int(header.get("NAXIS", 0))
        if naxis not in (2, 3):
            raise ValueError(f"Image FITS non prise en charge (NAXIS={naxis})")
        dims = [int(header[f"NAXIS{i}"]) for i in range(1, naxis + 1)]
        count = int(np.prod(dims))
        data = np.frombuffer(fh.read(count * abs(bitpix) // 8), dtype=_BITPIX_DTYPES[bitpix])
    data = data.reshape(dims[::-1])  # FITS is column-major: (NAXIS3, NAXIS2, NAXIS1)

    bzero = float(header.get("BZERO", 0.0))
    bscale = float(header.get("BSCALE", 1.0))
    if bitpix == 16 and bzero == 32768 and bscale == 1:
        data = (data.astype(np.int32) + 32768).astype(np.uint16)
    elif bitpix == 8 and bzero == 0 and bscale == 1:
        data = data.astype(np.uint8)
    elif bzero != 0 or bscale != 1:
        data = data.astype(np.float32) * bscale + bzero
    else:
        data = data.astype(data.dtype.newbyteorder("="))

    if naxis == 3:
        data = np.moveaxis(data, 0, -1)
        if data.shape[-1] == 1:
            data = data[..., 0]
    if str(header.get("ROWORDER", "TOP-DOWN")).upper() == "BOTTOM-UP":
        data = data[::-1]
    return np.ascontiguousarray(data), header


def write_fits(path: str, data: np.ndarray, extra: dict | None = None) -> None:
    """Write uint8, uint16 or float data (HxW or HxWx3). Rows are stored top-down."""
    data = np.asarray(data)
    if data.dtype == np.uint8:
        bitpix, out, bzero = 8, data.astype(">u1"), None
    elif data.dtype == np.uint16:
        bitpix, out, bzero = 16, (data.astype(np.int32) - 32768).astype(">i2"), 32768
    else:
        bitpix, out, bzero = -32, data.astype(">f4"), None

    if out.ndim == 3:
        out = np.moveaxis(out, -1, 0)
    cards = [_card("SIMPLE", True, "conforms to FITS standard"),
             _card("BITPIX", bitpix), _card("NAXIS", out.ndim)]
    for i, n in enumerate(out.shape[::-1], start=1):
        cards.append(_card(f"NAXIS{i}", n))
    if bzero is not None:
        cards += [_card("BZERO", bzero), _card("BSCALE", 1)]
    cards.append(_card("ROWORDER", "TOP-DOWN"))
    for key, value in (extra or {}).items():
        cards.append(_card(key.upper()[:8], value))
    cards.append(_card("END"))
    head = b"".join(cards)
    head += b" " * (-len(head) % BLOCK)
    body = np.ascontiguousarray(out).tobytes()
    body += b"\0" * (-len(body) % BLOCK)
    with open(path, "wb") as fh:
        fh.write(head)
        fh.write(body)
