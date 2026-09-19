"""Cheap content fingerprint used to confirm two files are really the same.

Size alone is a weak signal, and hashing a whole feature file costs more than
the answer is worth, so the fingerprint covers both ends of the file: enough
to separate two titles that share an identical header, at a fixed read cost.
"""
import hashlib

#: Bytes read from each end of the file.
EDGE_BYTES = 1024 * 1024


def edge_fingerprint(path: str, *, block: int = EDGE_BYTES) -> str | None:
    """Fingerprint the first and last ``block`` bytes of ``path``.

    Returns ``None`` when the file cannot be read, so an unmounted share or a
    vanished file is never reported as a duplicate of anything.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(block)
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - block))
            tail = handle.read(block)
    except OSError:
        return None

    digest = hashlib.sha256()
    digest.update(head)
    digest.update(tail)
    return digest.hexdigest()
