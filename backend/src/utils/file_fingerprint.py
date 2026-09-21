"""Cheap content fingerprint used to confirm two files are really the same.

Size alone is a weak signal, and hashing a whole feature file costs more than
the answer is worth, so the fingerprint covers both ends of the file: enough
to separate two titles that share an identical header, at a fixed read cost.

This is the one definition of that digest. Every storage must produce the same
value for the same bytes because the duplicate check compares fingerprints
across sources -- if one provider used MD5 and another SHA-256, a local copy
would silently never match its bucket twin.
"""
import hashlib

#: Bytes read from each end of the file.
EDGE_BYTES = 1024 * 1024


def hash_edges(head: bytes, tail: bytes) -> str:
    """Digest of the first and last ``EDGE_BYTES`` of a file, already read."""
    digest = hashlib.sha256()
    digest.update(head)
    digest.update(tail)
    return digest.hexdigest()


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

    return hash_edges(head, tail)
