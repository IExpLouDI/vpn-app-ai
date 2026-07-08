import asyncio
import struct

FRAME_HEADER = "!H"
FRAME_SIZE = struct.calcsize(FRAME_HEADER)


def frame_packet(data: bytes) -> bytes:
    return struct.pack(FRAME_HEADER, len(data)) + data


async def read_frame(reader: asyncio.StreamReader) -> bytes | None:
    try:
        raw = await reader.readexactly(FRAME_SIZE)
    except asyncio.IncompleteReadError:
        return None
    length = struct.unpack(FRAME_HEADER, raw)[0]
    try:
        return await reader.readexactly(length)
    except asyncio.IncompleteReadError:
        return None
