"""The one-line summary shown for each story: a real headline from it.

Nothing is generated. The summary is whichever member headline sits closest to
the middle of the story in embedding space, so it is always something an outlet
actually wrote, names spelled as they spelled them.
"""


def representative_title(titles, max_titles=12):
    """The story's most central headline.

    Duplicates are removed, the remaining headlines are embedded, and the one
    nearest their centroid is returned. Only the first max_titles are
    considered, which keeps a very large story cheap to summarise.
    """
    import numpy as np

    from backend.nlp.embeddings import model as embed_model

    cleaned, seen = [], set()
    for title in list(titles)[:max_titles]:
        text = " ".join((title or "").split())
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)

    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]

    vectors = np.asarray(embed_model.encode(cleaned, normalize_embeddings=True))
    centroid = vectors.mean(axis=0)
    return cleaned[int((vectors @ centroid).argmax())]
