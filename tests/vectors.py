# tests/vectors.py — wire-format vectors for the Nibe UART frame core.
# Frame layout (see components/heatwhisper/heatwhisper.cpp): [5C, X, ADDR, CMD, LEN, DATA.., CHK]
# LEN lives at index 4, CHK at index LEN+5, CHK = XOR over indices [2..LEN+4].
# Read-request for 40004 (0x9C44, LE bytes 44 9C): 5C 00 C0 69 02 44 9C CRC
# CRC = C0^69^02^44^9C
READ_40004 = bytes([0x5C, 0x00, 0xC0, 0x69, 0x02, 0x44, 0x9C,
                    0xC0 ^ 0x69 ^ 0x02 ^ 0x44 ^ 0x9C])
CORRUPT = bytes([0x5C, 0x00, 0xC0, 0x69, 0x02, 0x44, 0x9C, 0x00])
# Known-good slave write-response frame (C0-framed: LEN at [2], CHK = XOR over [0..LEN+2]).
# Ref: reference-project/backend.js:37. CHK 0x6F = XOR of the first 9 bytes.
WRITE_EXAMPLE = bytes([192, 107, 6, 115, 176, 1, 0, 0, 0, 111])
