# components/heatwhisper/modbus_rtu.py — Python reference for the C++ master (mirrored 1:1).
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

def _head(addr: int, fc: int, reg: int) -> bytes:
    wire = reg - 1  # full 1-based number -> wire address (40004 -> 0x9C43)
    return bytes([addr & 0xFF, fc & 0xFF, (wire >> 8) & 0xFF, wire & 0xFF])

def build_read(addr: int, fc: int, reg: int, count: int) -> bytes:
    body = _head(addr, fc, reg) + bytes([(count >> 8) & 0xFF, count & 0xFF])
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])

def build_write_single(addr: int, reg: int, value: int) -> bytes:
    body = _head(addr, 0x06, reg) + bytes([(value >> 8) & 0xFF, value & 0xFF])
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])

def build_write_multi(addr: int, reg: int, values: list) -> bytes:
    body = (_head(addr, 0x10, reg) + bytes([(len(values) >> 8) & 0xFF, len(values) & 0xFF,
                                            2 * len(values)])
            + b"".join(bytes([(v >> 8) & 0xFF, v & 0xFF]) for v in values))
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])

def parse_read_response(frame: bytes, fc: int, count: int) -> list:
    if frame[1] != fc or frame[2] != 2 * count:
        raise ValueError("function-code/length mismatch")
    body, got = frame[:-2], frame[-2] | (frame[-1] << 8)
    if crc16(body) != got:
        raise ValueError("CRC mismatch")
    return [(frame[3 + 2 * i] << 8) | frame[4 + 2 * i] for i in range(count)]

def decode_be(words: list, size: str, factor: int, word_order: str) -> float:
    f = factor or 1
    if size in ("u16", "s16"):
        raw = words[0]
        if size == "s16" and raw >= 32768:
            raw -= 65536
        return raw / f
    if word_order == "CDAB":
        words = [words[1], words[0]]
    u = (words[0] << 16) | words[1]
    return (u - 4294967296 if size == "s32" and u >= 2147483648 else u) / f
