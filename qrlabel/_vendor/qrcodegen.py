# QR Code generator library (vendored, pure Python)
#
# Adapted from the Project Nayuki "QR Code generator library" (Python),
# which is Copyright (c) Project Nayuki, distributed under the MIT License:
# https://www.nayuki.io/page/qr-code-generator-library
#
# This vendored copy is trimmed and slightly reorganized for the
# qr-label-maker tool, but the algorithm, constants and tables are kept
# faithful to the original so that output remains fully standard-compliant
# (QR Code Model 2, ISO/IEC 18004). The original MIT permission notice is
# included here as required by that license.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# - The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
# - THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
#   THE SOFTWARE.

import collections
import re
from collections.abc import Callable, Sequence

MIN_VERSION = 1
MAX_VERSION = 40

_PENALTY_N1 = 3
_PENALTY_N2 = 3
_PENALTY_N3 = 40
_PENALTY_N4 = 10

_ECC_CODEWORDS_PER_BLOCK: Sequence[Sequence[int]] = (
    # 0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, ...
    (-1,  7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),  # Low
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),  # Medium
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),  # Quartile
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),  # High
)

_NUM_ERROR_CORRECTION_BLOCKS: Sequence[Sequence[int]] = (
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4,  4,  4,  4,  4,  6,  6,  6,  6,  7,  8,  8,  9,  9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),  # Low
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5,  5,  8,  9,  9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),  # Medium
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8,  8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),  # Quartile
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),  # High
)

_MASK_PATTERNS: Sequence[Callable[[int, int], int]] = (
    (lambda x, y: (x + y) % 2),
    (lambda x, y: y % 2),
    (lambda x, y: x % 3),
    (lambda x, y: (x + y) % 3),
    (lambda x, y: (x // 3 + y // 2) % 2),
    (lambda x, y: x * y % 2 + x * y % 3),
    (lambda x, y: (x * y % 2 + x * y % 3) % 2),
    (lambda x, y: ((x + y) % 2 + x * y % 3) % 2),
)


class Ecc:
    """Error correction level of a QR Code symbol (immutable)."""

    LOW = None
    MEDIUM = None
    QUARTILE = None
    HIGH = None

    def __init__(self, i: int, fb: int) -> None:
        self.ordinal = i
        self.formatbits = fb  # Value stored in format bits for this level


Ecc.LOW = Ecc(0, 1)      # ~7% recovery
Ecc.MEDIUM = Ecc(1, 0)   # ~15% recovery
Ecc.QUARTILE = Ecc(2, 3)  # ~25% recovery
Ecc.HIGH = Ecc(3, 2)     # ~30% recovery

ECC_LEVELS = (Ecc.LOW, Ecc.MEDIUM, Ecc.QUARTILE, Ecc.HIGH)
ECC_NAME_TO_LEVEL = {"L": Ecc.LOW, "M": Ecc.MEDIUM, "Q": Ecc.QUARTILE, "H": Ecc.HIGH}


class Mode:
    """Encoding mode of a QR segment (immutable)."""

    NUMERIC = None
    ALPHANUMERIC = None
    BYTE = None
    KANJI = None
    ECI = None

    def __init__(self, modebits: int, charcounts: tuple) -> None:
        self._modebits = modebits
        self._charcounts = charcounts

    def get_mode_bits(self) -> int:
        return self._modebits

    def num_char_count_bits(self, ver: int) -> int:
        return self._charcounts[(ver + 7) // 17]


Mode.NUMERIC = Mode(0x1, (10, 12, 14))
Mode.ALPHANUMERIC = Mode(0x2, (9, 11, 13))
Mode.BYTE = Mode(0x4, (8, 16, 16))
Mode.KANJI = Mode(0x8, (8, 10, 12))
Mode.ECI = Mode(0x7, (0, 0, 0))


class QrSegment:
    """A segment of character/binary/control data in a QR Code symbol (immutable)."""

    _NUMERIC_REGEX = re.compile(r"[0-9]*")
    _ALPHANUMERIC_REGEX = re.compile(r"[A-Z0-9 $%*+./:-]*")
    _ALPHANUMERIC_ENCODING_TABLE = {ch: i for (i, ch) in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:")}

    def __init__(self, mode: Mode, numch: int, bitdata: Sequence[int]) -> None:
        if numch < 0:
            raise ValueError()
        self._mode = mode
        self._numchars = numch
        self._bitdata = list(bitdata)

    def get_mode(self) -> Mode:
        return self._mode

    def get_num_chars(self) -> int:
        return self._numchars

    def get_data(self) -> list:
        return list(self._bitdata)

    @staticmethod
    def make_bytes(data) -> "QrSegment":
        bb = _BitBuffer()
        for b in data:
            bb.append_bits(b, 8)
        return QrSegment(Mode.BYTE, len(data), bb)

    @staticmethod
    def make_numeric(digits: str) -> "QrSegment":
        if QrSegment._NUMERIC_REGEX.fullmatch(digits) is None:
            raise ValueError("String contains non-numeric characters")
        bb = _BitBuffer()
        i = 0
        while i < len(digits):
            n = min(len(digits) - i, 3)
            bb.append_bits(int(digits[i:i + n]), n * 3 + 1)
            i += n
        return QrSegment(Mode.NUMERIC, len(digits), bb)

    @staticmethod
    def make_alphanumeric(text: str) -> "QrSegment":
        if QrSegment._ALPHANUMERIC_REGEX.fullmatch(text) is None:
            raise ValueError("String contains unencodable characters in alphanumeric mode")
        bb = _BitBuffer()
        for i in range(0, len(text) - 1, 2):
            temp = QrSegment._ALPHANUMERIC_ENCODING_TABLE[text[i]] * 45
            temp += QrSegment._ALPHANUMERIC_ENCODING_TABLE[text[i + 1]]
            bb.append_bits(temp, 11)
        if len(text) % 2 > 0:
            bb.append_bits(QrSegment._ALPHANUMERIC_ENCODING_TABLE[text[-1]], 6)
        return QrSegment(Mode.ALPHANUMERIC, len(text), bb)

    @staticmethod
    def make_segments(text: str) -> list:
        """Chooses the most compact encoding for the given text."""
        if text == "":
            segs = []
        elif QrSegment._NUMERIC_REGEX.fullmatch(text) is not None:
            segs = [QrSegment.make_numeric(text)]
        elif QrSegment._ALPHANUMERIC_REGEX.fullmatch(text) is not None:
            segs = [QrSegment.make_alphanumeric(text)]
        else:
            segs = [QrSegment.make_bytes(text.encode("utf-8"))]
        return segs

    @staticmethod
    def get_total_bits(segs: Sequence["QrSegment"], version: int):
        result = 0
        for seg in segs:
            ccbits = seg.get_mode().num_char_count_bits(version)
            if seg.get_num_chars() >= (1 << ccbits):
                return None
            result += 4 + ccbits + len(seg._bitdata)
        return result


class _BitBuffer(list):
    """Appendable sequence of bits (0s and 1s)."""

    def append_bits(self, val: int, n: int) -> None:
        if n < 0 or val >> n != 0:
            raise ValueError("Value out of range")
        self.extend(((val >> i) & 1) for i in reversed(range(n)))


class QrCode:
    """A QR Code symbol (immutable square grid of dark/light cells).
    Supports QR Code Model 2, versions 1 to 40, all 4 ECC levels."""

    # ---- High-level constructors ----

    @staticmethod
    def encode_text(text: str, ecl: Ecc) -> "QrCode":
        return QrCode.encode_segments(QrSegment.make_segments(text), ecl)

    @staticmethod
    def encode_binary(data, ecl: Ecc) -> "QrCode":
        return QrCode.encode_segments([QrSegment.make_bytes(data)], ecl)

    @staticmethod
    def encode_segments(segs: Sequence[QrSegment], ecl: Ecc, minversion: int = 1,
                        maxversion: int = MAX_VERSION, mask: int = -1, boostecl: bool = True) -> "QrCode":
        """Returns a QR Code with the smallest version that holds the data."""
        if not (MIN_VERSION <= minversion <= maxversion <= MAX_VERSION) or not (-1 <= mask <= 7):
            raise ValueError("Invalid value")

        for version in range(minversion, maxversion + 1):
            datacapacitybits = num_data_codewords(version, ecl) * 8
            datausedbits = QrSegment.get_total_bits(segs, version)
            if datausedbits is not None and datausedbits <= datacapacitybits:
                break
            if version >= maxversion:
                msg = "Segment too long"
                if datausedbits is not None:
                    msg = f"Data length = {datausedbits} bits, Max capacity = {datacapacitybits} bits"
                raise DataTooLongError(msg)
        assert datausedbits is not None

        # Boost ECC level if the data still fits in the same version
        for newecl in (Ecc.MEDIUM, Ecc.QUARTILE, Ecc.HIGH):
            if boostecl and datausedbits <= num_data_codewords(version, newecl) * 8:
                ecl = newecl

        bb = _BitBuffer()
        for seg in segs:
            bb.append_bits(seg.get_mode().get_mode_bits(), 4)
            bb.append_bits(seg.get_num_chars(), seg.get_mode().num_char_count_bits(version))
            bb.extend(seg._bitdata)
        assert len(bb) == datausedbits

        datacapacitybits = num_data_codewords(version, ecl) * 8
        bb.append_bits(0, min(4, datacapacitybits - len(bb)))
        bb.append_bits(0, -len(bb) % 8)
        assert len(bb) % 8 == 0
        i = 0
        while len(bb) < datacapacitybits:
            bb.append_bits((0xEC, 0x11)[i % 2], 8)
            i += 1
        assert len(bb) == datacapacitybits

        datacodewords = bytearray([0] * (len(bb) // 8))
        for i, bit in enumerate(bb):
            datacodewords[i >> 3] |= bit << (7 - (i & 7))

        return QrCode(version, ecl, datacodewords, mask)

    # ---- Constructor (low level) ----

    def __init__(self, version: int, errcorlvl: Ecc, datacodewords, msk: int) -> None:
        if not (MIN_VERSION <= version <= MAX_VERSION):
            raise ValueError("Version value out of range")
        if not (-1 <= msk <= 7):
            raise ValueError("Mask value out of range")

        self._version = version
        self._size = version * 4 + 17
        self._errcorlvl = errcorlvl

        self._modules = [[False] * self._size for _ in range(self._size)]
        self._isfunction = [[False] * self._size for _ in range(self._size)]

        self._draw_function_patterns()
        allcodewords = self._add_ecc_and_interleave(bytearray(datacodewords))
        self._draw_codewords(allcodewords)

        if msk == -1:  # Automatically choose the best mask
            minpenalty = 1 << 32
            for i in range(8):
                self._apply_mask(i)
                self._draw_format_bits(i)
                penalty = self._get_penalty_score()
                if penalty < minpenalty:
                    msk = i
                    minpenalty = penalty
                self._apply_mask(i)  # Undoes the mask (XOR)
        assert 0 <= msk <= 7
        self._mask = msk
        self._apply_mask(msk)
        self._draw_format_bits(msk)
        del self._isfunction

    # ---- Accessors ----

    def get_version(self) -> int:
        return self._version

    def get_size(self) -> int:
        return self._size

    def get_error_correction_level(self) -> Ecc:
        return self._errcorlvl

    def get_mask(self) -> int:
        return self._mask

    def get_module(self, x: int, y: int) -> bool:
        """False = light module, True = dark module. Origin (0,0) is top left."""
        return 0 <= x < self._size and 0 <= y < self._size and self._modules[y][x]

    def to_matrix(self) -> list:
        """Returns the module grid as a copy; row[y][x], False = light, True = dark."""
        return [row[:] for row in self._modules]

    # ---- Drawing function patterns ----

    def _draw_function_patterns(self) -> None:
        # Timing patterns
        for i in range(self._size):
            self._set_function_module(6, i, i % 2 == 0)
            self._set_function_module(i, 6, i % 2 == 0)

        # Finder patterns (overwrites some timing modules)
        self._draw_finder_pattern(3, 3)
        self._draw_finder_pattern(self._size - 4, 3)
        self._draw_finder_pattern(3, self._size - 4)

        # Alignment patterns
        alignpatpos = self._get_alignment_pattern_positions()
        numalign = len(alignpatpos)
        skips = ((0, 0), (0, numalign - 1), (numalign - 1, 0))
        for i in range(numalign):
            for j in range(numalign):
                if (i, j) not in skips:  # Skip the three finder corners
                    self._draw_alignment_pattern(alignpatpos[i], alignpatpos[j])

        self._draw_format_bits(0)  # Dummy mask; overwritten later
        self._draw_version()

    def _draw_format_bits(self, mask: int) -> None:
        data = self._errcorlvl.formatbits << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        assert bits >> 15 == 0

        # First copy
        for i in range(0, 6):
            self._set_function_module(8, i, get_bit(bits, i))
        self._set_function_module(8, 7, get_bit(bits, 6))
        self._set_function_module(8, 8, get_bit(bits, 7))
        self._set_function_module(7, 8, get_bit(bits, 8))
        for i in range(9, 15):
            self._set_function_module(14 - i, 8, get_bit(bits, i))

        # Second copy
        for i in range(0, 8):
            self._set_function_module(self._size - 1 - i, 8, get_bit(bits, i))
        for i in range(8, 15):
            self._set_function_module(8, self._size - 15 + i, get_bit(bits, i))
        self._set_function_module(8, self._size - 8, True)  # Always dark

    def _draw_version(self) -> None:
        if self._version < 7:
            return
        rem = self._version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self._version << 12 | rem
        assert bits >> 18 == 0
        for i in range(18):
            bit = get_bit(bits, i)
            a = self._size - 11 + i % 3
            b = i // 3
            self._set_function_module(a, b, bit)
            self._set_function_module(b, a, bit)

    def _draw_finder_pattern(self, x: int, y: int) -> None:
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = x + dx, y + dy
                if 0 <= xx < self._size and 0 <= yy < self._size:
                    self._set_function_module(xx, yy, max(abs(dx), abs(dy)) not in (2, 4))

    def _draw_alignment_pattern(self, x: int, y: int) -> None:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self._set_function_module(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)

    def _set_function_module(self, x: int, y: int, isdark: bool) -> None:
        self._modules[y][x] = isdark
        self._isfunction[y][x] = True

    # ---- Codewords and masking ----

    def _add_ecc_and_interleave(self, data: bytearray) -> bytes:
        version = self._version
        assert len(data) == num_data_codewords(version, self._errcorlvl)

        numblocks = _NUM_ERROR_CORRECTION_BLOCKS[self._errcorlvl.ordinal][version]
        blockecclen = _ECC_CODEWORDS_PER_BLOCK[self._errcorlvl.ordinal][version]
        rawcodewords = num_raw_data_modules(version) // 8
        numshortblocks = numblocks - rawcodewords % numblocks
        shortblocklen = rawcodewords // numblocks

        blocks = []
        rsdiv = reed_solomon_compute_divisor(blockecclen)
        k = 0
        for i in range(numblocks):
            dat = data[k:k + shortblocklen - blockecclen + (0 if i < numshortblocks else 1)]
            k += len(dat)
            ecc = reed_solomon_compute_remainder(dat, rsdiv)
            if i < numshortblocks:
                dat.append(0)
            blocks.append(dat + ecc)
        assert k == len(data)

        result = bytearray()
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                if (i != shortblocklen - blockecclen) or (j >= numshortblocks):
                    result.append(blk[i])
        assert len(result) == rawcodewords
        return result

    def _draw_codewords(self, data: bytes) -> None:
        assert len(data) == num_raw_data_modules(self._version) // 8
        i = 0
        for right in range(self._size - 1, 0, -2):
            if right <= 6:
                right -= 1
            for vert in range(self._size):
                for j in range(2):
                    x = right - j
                    upward = (right + 1) & 2 == 0
                    y = (self._size - 1 - vert) if upward else vert
                    if not self._isfunction[y][x] and i < len(data) * 8:
                        self._modules[y][x] = get_bit(data[i >> 3], 7 - (i & 7))
                        i += 1
        assert i == len(data) * 8

    def _apply_mask(self, mask: int) -> None:
        if not 0 <= mask <= 7:
            raise ValueError("Mask value out of range")
        masker = _MASK_PATTERNS[mask]
        for y in range(self._size):
            for x in range(self._size):
                self._modules[y][x] ^= (masker(x, y) == 0) and not self._isfunction[y][x]

    def _get_penalty_score(self) -> int:
        result = 0
        size = self._size
        modules = self._modules

        for y in range(size):  # Rows: run lengths and finder-like patterns
            runcolor = False
            runx = 0
            runhistory = collections.deque([0] * 7, 7)
            for x in range(size):
                if modules[y][x] == runcolor:
                    runx += 1
                    if runx == 5:
                        result += _PENALTY_N1
                    elif runx > 5:
                        result += 1
                else:
                    _finder_penalty_add_history(runx, runhistory, size)
                    if not runcolor:
                        result += _finder_penalty_count_patterns(runhistory, size) * _PENALTY_N3
                    runcolor = modules[y][x]
                    runx = 1
            result += _finder_penalty_terminate_and_count(runcolor, runx, runhistory, size) * _PENALTY_N3
        for x in range(size):  # Columns
            runcolor = False
            runy = 0
            runhistory = collections.deque([0] * 7, 7)
            for y in range(size):
                if modules[y][x] == runcolor:
                    runy += 1
                    if runy == 5:
                        result += _PENALTY_N1
                    elif runy > 5:
                        result += 1
                else:
                    _finder_penalty_add_history(runy, runhistory, size)
                    if not runcolor:
                        result += _finder_penalty_count_patterns(runhistory, size) * _PENALTY_N3
                    runcolor = modules[y][x]
                    runy = 1
            result += _finder_penalty_terminate_and_count(runcolor, runy, runhistory, size) * _PENALTY_N3

        # 2x2 blocks of same color
        for y in range(size - 1):
            for x in range(size - 1):
                if modules[y][x] == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                    result += _PENALTY_N2

        # Balance of dark and light modules
        dark = sum(1 if cell else 0 for row in modules for cell in row)
        total = size ** 2
        k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        assert 0 <= k <= 9
        result += k * _PENALTY_N4
        return result

    def _get_alignment_pattern_positions(self) -> list:
        if self._version == 1:
            return []
        numalign = self._version // 7 + 2
        step = (self._version * 8 + numalign * 3 + 5) // (numalign * 4 - 4) * 2
        result = [(self._size - 7 - i * step) for i in range(numalign - 1)] + [6]
        return list(reversed(result))


# ---- Stateless helper functions (public, version/ECC math) ----

def num_raw_data_modules(ver: int) -> int:
    """Number of modules not used by function patterns (includes remainder bits)."""
    if not MIN_VERSION <= ver <= MAX_VERSION:
        raise ValueError("Version number out of range")
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        numalign = ver // 7 + 2
        result -= (25 * numalign - 10) * numalign - 55
        if ver >= 7:
            result -= 36
    assert 208 <= result <= 29648
    return result


def num_data_codewords(ver: int, ecl: Ecc) -> int:
    """Number of data (not error correction) codewords at version+ECC level."""
    return num_raw_data_modules(ver) // 8 \
        - _ECC_CODEWORDS_PER_BLOCK[ecl.ordinal][ver] \
        * _NUM_ERROR_CORRECTION_BLOCKS[ecl.ordinal][ver]


def reed_solomon_compute_divisor(degree: int) -> bytes:
    """Reed-Solomon generator polynomial coefficients, highest power first
    (excluding the always-1 leading term)."""
    if not 1 <= degree <= 255:
        raise ValueError("Degree out of range")
    result = bytearray([0] * (degree - 1) + [1])
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = reed_solomon_multiply(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = reed_solomon_multiply(root, 0x02)
    return result


def reed_solomon_compute_remainder(data: bytes, divisor: bytes) -> bytes:
    result = bytearray([0] * len(divisor))
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= reed_solomon_multiply(coef, factor)
    return result


def reed_solomon_multiply(x: int, y: int) -> int:
    """Product of two field elements in GF(2^8/0x11D)."""
    if x >> 8 != 0 or y >> 8 != 0:
        raise ValueError("Byte out of range")
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    assert z >> 8 == 0
    return z


def get_bit(x: int, i: int) -> bool:
    return (x >> i) & 1 != 0


def _finder_penalty_count_patterns(runhistory: collections.deque, size: int) -> int:
    n = runhistory[1]
    assert n <= size * 3
    core = n > 0 and (runhistory[2] == runhistory[4] == runhistory[5] == n) and runhistory[3] == n * 3
    return (1 if core and runhistory[0] >= n * 4 and runhistory[6] >= n else 0) \
        + (1 if core and runhistory[6] >= n * 4 and runhistory[0] >= n else 0)


def _finder_penalty_terminate_and_count(currentruncolor: bool, currentrunlength: int,
                                        runhistory: collections.deque, size: int) -> int:
    if currentruncolor:  # Terminate dark run
        _finder_penalty_add_history(currentrunlength, runhistory, size)
        currentrunlength = 0
    currentrunlength += size  # Add light border to final run
    _finder_penalty_add_history(currentrunlength, runhistory, size)
    return _finder_penalty_count_patterns(runhistory, size)


def _finder_penalty_add_history(currentrunlength: int, runhistory: collections.deque, size: int) -> None:
    if runhistory[0] == 0:
        currentrunlength += size  # Add light border to initial run
    runhistory.appendleft(currentrunlength)


class DataTooLongError(ValueError):
    """Raised when the supplied data cannot fit any QR Code version."""
    pass
