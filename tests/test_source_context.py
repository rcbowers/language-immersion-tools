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
