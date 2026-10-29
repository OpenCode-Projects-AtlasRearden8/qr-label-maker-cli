import sys

from ._vendor import qrcodegen as _g
from ._vendor.qrcodegen import DataTooLongError, Ecc, QrSegment, QrCode  # noqa: F401 (re-exports)


def encode_matrix(text, ecl="M"):
    """Encode text into a QR Code module matrix.

    Returns a dict with keys:
      matrix  - list of rows; module (x, y) at matrix[y][x], True = dark
      size    - modules per side (version * 4 + 17)
      version - QR version (1..40)
      mask    - mask pattern used (0..7)
      ecl     - the error correction level actually used (may be boosted)
    """
    if not isinstance(ecl, str) or ecl.upper() not in _g.ECC_NAME_TO_LEVEL:
        raise ValueError(f"Unknown ECC level: {ecl!r} (use L, M, Q or H)")
    code = _g.QrCode.encode_text(text, _g.ECC_NAME_TO_LEVEL[ecl.upper()])
    return {
        "matrix": code.to_matrix(),
        "size": code.get_size(),
        "version": code.get_version(),
        "mask": code.get_mask(),
        "ecl": code.get_error_correction_level().ordinal,
    }
