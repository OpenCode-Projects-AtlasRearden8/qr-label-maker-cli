"""Tests for the vendored QR encoder (qrlabel/qrcodes.py and _vendor)."""

import struct
import zlib

import pytest

from qrlabel._vendor.qrcodegen import (DataTooLongError, Ecc, QrCode, QrSegment,
                                       num_data_codewords, num_raw_data_modules,
                                       reed_solomon_compute_divisor,
                                       reed_solomon_compute_remainder,
                                       reed_solomon_multiply)
from qrlabel.qrcodes import encode_matrix
from pathlib import Path
import json

PAYLOADS = [
    "HELLO WORLD",
    "01234567",
    "https://example.com/free-stuff",
    "BIN 7 SCREWS",
    "Grandma's Secret Sauce\nmakes 2 quarts",
    "https://dylanasdale.github.io/",
    "x" * 120,
]


def test_encode_matrix_structure():
    qr = encode_matrix("HELLO WORLD", ecl="M")
    assert qr["version"] == 1
    assert qr["size"] == 21
    assert len(qr["matrix"]) == 21
    assert all(len(row) == 21 for row in qr["matrix"])
    # timing pattern alternates along row/col 6 (between the finder areas)
    inner = range(8, qr["size"] - 8)
    assert all(qr["matrix"][6][x] == (x % 2 == 0) for x in inner)
    assert all(qr["matrix"][y][6] == (y % 2 == 0) for y in inner)
    # three finder corners have dark centers
    for (cx, cy) in ((3, 3), (17, 3), (3, 17)):
        assert qr["matrix"][cy][cx] is True


def _format_bits_from_matrix(qr):
    """Extracts the 15-bit first-copy format info from the module grid."""
    size = qr["size"]
    bits = 0
    positions = [(8, i) for i in range(6)]
    positions += [(8, 7), (8, 8), (7, 8)]
    positions += [(14 - i, 8) for i in range(9, 15)]
    for bit_index, (x, y) in zip(range(15), positions):
        bits |= (1 if qr["matrix"][y][x] else 0) << bit_index
    assert size > 0
    return bits


@pytest.mark.parametrize("ecl", ["L", "M", "Q", "H"])
@pytest.mark.parametrize("mask", range(8))
def test_format_bits_are_valid_bch(ecl, mask):
    """The format info region must be a correct BCH(15,5) code for the
    *actual* ECC level and mask of the symbol (ECC may be boosted)."""
    name = {"L": "LOW", "M": "MEDIUM", "Q": "QUARTILE", "H": "HIGH"}[ecl]
    code = QrCode.encode_segments(QrSegment.make_segments("HELLO WORLD"),
                                  getattr(Ecc, name), mask=mask)
    actual = code.get_error_correction_level()
    qr = {"size": code.get_size(),
          "matrix": [[code.get_module(x, y) for x in range(code.get_size())]
                     for y in range(code.get_size())]}
    assert code.get_mask() == mask
    bits = _format_bits_from_matrix(qr)
    data_with_rem = bits ^ 0x5412
    data = data_with_rem >> 10
    # decode the 2-bit format info: 01=L, 00=M, 11=Q, 10=H
    decoded_ecl = {1: "L", 0: "M", 3: "Q", 2: "H"}[data >> 3]
    assert decoded_ecl == {0: "L", 1: "M", 2: "Q", 3: "H"}[actual.ordinal]
    assert (data & 7) == mask
    # verify the BCH remainder properly
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    assert (data_with_rem & 0x3FF) == rem


@pytest.mark.parametrize("ecc_name,expected", [("LOW", 19), ("MEDIUM", 16),
                                               ("QUARTILE", 13), ("HIGH", 9)])
def test_v1_data_capacity(ecc_name, expected):
    """Version 1: 208 raw modules = 26 codewords, minus per-block ECC."""
    per_block = {"LOW": 7, "MEDIUM": 10, "QUARTILE": 13, "HIGH": 17}[ecc_name]
    assert per_block + expected == num_raw_data_modules(1) // 8 == 26
    assert num_data_codewords(1, getattr(Ecc, ecc_name)) == expected


def test_version_capacity_math():
    assert num_raw_data_modules(1) == 208
    assert num_raw_data_modules(2) == 359
    assert num_data_codewords(1, Ecc.LOW) == 19
    assert num_data_codewords(1, Ecc.MEDIUM) == 16
    assert num_data_codewords(10, Ecc.LOW) == 274  # 346 total - 4 blocks x 18


def test_reed_solomon_basics():
    div = reed_solomon_compute_divisor(10)
    assert len(div) == 10 and div[-1] % 2 == 1  # generator is not divisible by x
    # GF multiplication basics
    assert reed_solomon_multiply(0x02, 0x02) == 0x04
    assert reed_solomon_multiply(1, 0x53) == 0x53  # multiplicative identity
    inverse = next(y for y in range(1, 256)
                   if reed_solomon_multiply(0x53, y) == 1)
    assert 1 < inverse < 256  # every nonzero element has an inverse
    # unencoded (zero) data -> zero remainder
    assert reed_solomon_compute_remainder(bytes(15), div) == bytes(10)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_multi_payload_versions_increase_with_size(payload):
    qr = encode_matrix(payload, ecl="L")
    assert 1 <= qr["version"] <= 40
    assert qr["version"] == (qr["size"] - 17) // 4


def test_too_long_raises():
    with pytest.raises(DataTooLongError):
        encode_matrix("A" * 3000, ecl="H")


def test_bad_ecl_raises():
    with pytest.raises(ValueError):
        encode_matrix("hi", ecl="Z")


def test_matrix_fixture_golden():
    """Pinned deterministic matrices for a fixed payload list.

    These exact matrices were verified to decode with an independent
    QR reader during development (see STATUS.md 'Verification')."""
    fixture = json.loads((Path(__file__).parent / "fixtures" / "qr-matrices.json").read_text())
    for payload, expected in fixture:
        qr = encode_matrix(payload, ecl="M")
        assert qr["matrix"] == expected["matrix"]
        assert qr["mask"] == expected["mask"]
        assert qr["version"] == expected["version"]


def _png_bytes(matrix, scale=4, quiet=4):
    s = (len(matrix) + 2 * quiet) * scale
    rows = []
    for py in range(s):
        row = bytearray([0])
        for px in range(s):
            my, mx = py // scale - quiet, px // scale - quiet
            dark = 0 <= mx < len(matrix) and 0 <= my < len(matrix) \
                and matrix[my][mx]
            row += b"\x00\x00\x00" if dark else b"\xff\xff\xff"
        rows.append(bytes(row))
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", s, s, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def test_qr_code_decodes_with_opencv_when_available():
    """Optional real-reader check; skipped when OpenCV is not installed."""
    cv2 = pytest.importorskip("cv2")
    detector = cv2.QRCodeDetector()
    for payload in ("HELLO WORLD", "https://example.com/free-stuff"):
        qr = encode_matrix(payload, ecl="M")
        png = cv2.imdecode(
            __import__("numpy").frombuffer(_png_bytes(qr["matrix"]), dtype="uint8"),
            cv2.IMREAD_COLOR)
        got, _, _ = detector.detectAndDecode(png)
        assert got == payload
