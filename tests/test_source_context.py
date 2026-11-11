from immersion_app.media import source_context
from immersion_app.media.source_context import extract_url_contexts

HTML = """<html><head><title>Noticia</title><script>var x = "no.";</script></head>
<body><nav>Menu. Inicio.</nav>
<p>Intro fuera.</p>
<article><h1>Titular</h1><p>Primera frase. Segunda frase!</p><p>Tercera.</p></article>
<footer>Pie.</footer></body></html>"""


def test_extract_url_contexts_prefers_article_and_splits_sentences():
    contexts = extract_url_contexts("https://example.com/a", fetch=lambda url: HTML)

    assert [(c.text, c.source_name, c.location) for c in contexts] == [
        ("Titular", "Noticia", "Paragraph 1"),
        ("Primera frase.", "Noticia", "Paragraph 2"),
        ("Segunda frase!", "Noticia", "Paragraph 2"),
        ("Tercera.", "Noticia", "Paragraph 3"),
    ]


def test_extract_url_contexts_falls_back_to_body_and_hostname():
    html = "<body><p>Hola mundo.</p><script>ignored()</script></body>"

    contexts = extract_url_contexts("https://example.com/a", fetch=lambda url: html)

    assert [(c.text, c.source_name) for c in contexts] == [("Hola mundo.", "example.com")]


def test_load_source_contexts_dispatches_urls(monkeypatch):
    monkeypatch.setattr(source_context, "extract_url_contexts", lambda url: [url])

    assert source_context.load_source_contexts("https://example.com/a") == ["https://example.com/a"]


def test_extract_epub_contexts_yields_sentences_with_page_locations(make_epub):
    contexts = source_context.extract_epub_contexts(make_epub(chapters=1, paragraphs=3))

    assert contexts
    assert all(c.source_name == "libro.epub" for c in contexts)
    assert contexts[0].location == "Page 1"
    assert any(c.text.startswith("Hola mundo, esto es la frase 0") for c in contexts)


def test_load_source_contexts_dispatches_epub(make_epub):
    contexts = source_context.load_source_contexts(make_epub(chapters=1, paragraphs=2))

    assert contexts and contexts[0].location == "Page 1"


def test_extract_pdf_contexts_groups_sentences_by_page(tmp_path):
    import pymupdf

    path = tmp_path / "libro.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((40, 60), "Hola mundo. Adios.", fontsize=12)
    doc.new_page().insert_text((40, 60), "Segunda pagina.", fontsize=12)
    doc.save(str(path))
    doc.close()

    contexts = source_context.load_source_contexts(path)

    assert [(c.text, c.location) for c in contexts] == [
        ("Hola mundo.", "Page 1"),
        ("Adios.", "Page 1"),
        ("Segunda pagina.", "Page 2"),
    ]


def test_load_source_contexts_rejects_unknown_suffix(tmp_path):
    import pytest

    path = tmp_path / "x.docx"
    path.write_text("x")

    with pytest.raises(ValueError, match=r"\.pdf, \.epub or \.srt"):
        source_context.load_source_contexts(path)
