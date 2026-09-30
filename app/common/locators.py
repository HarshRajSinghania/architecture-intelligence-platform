"""Locator sanitisation shared by the public evidence projection and the import report."""


def sanitize_source_locator(source_file: str | None) -> str | None:
    """Spec §11.2: return `source_file` unchanged only when it is the literal `opentelemetry` or a
    relative POSIX-style path containing no empty, `.` or `..` segment; otherwise `None`. Never
    rewrites an absolute path into a plausible public path, and never returns URI user-info, query
    parameters or fragments - those simply fail the "relative POSIX path" test and become `None`."""
    if source_file is None:
        return None
    if source_file == "opentelemetry":
        return source_file
    if (
        source_file.startswith("/")
        or "\\" in source_file
        or "?" in source_file
        or "#" in source_file
    ):
        return None
    segments = source_file.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        return None
    return source_file
