def bounded_query(*parts: str | None, max_chars: int = 500) -> str:
    """Build a whitespace-normalized query that cannot exceed provider limits."""

    query = " ".join(" ".join(str(part or "").split()) for part in parts).strip()
    if len(query) <= max_chars:
        return query
    shortened = query[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return shortened or query[:max_chars]
