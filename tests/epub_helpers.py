"""Build tiny synthetic EPUB files for tests (no binary fixtures checked in)."""

from __future__ import annotations

import zipfile
from pathlib import Path


def build_epub(path: Path, chapters: int = 2, paragraphs: int = 60) -> Path:
    """Write a minimal valid EPUB 3 (nav TOC + ``chapters`` XHTML chapters) to ``path``."""
    with zipfile.ZipFile(path, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        epub.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )
        items = "".join(
            f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(chapters)
        )
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(chapters))
        epub.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier>'
            "<dc:title>Libro</dc:title><dc:language>es</dc:language></metadata>"
            '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            f"{items}</manifest><spine>{spine}</spine></package>",
        )
        toc = "".join(f'<li><a href="c{i}.xhtml">Capitulo {i + 1}</a></li>' for i in range(chapters))
        epub.writestr(
            "OEBPS/nav.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>'
            f'<nav epub:type="toc"><ol>{toc}</ol></nav></body></html>',
        )
        for i in range(chapters):
            body = "".join(
                f"<p>Hola mundo, esto es la frase {j} del capitulo {i + 1}. Otra frase aqui.</p>"
                for j in range(paragraphs)
            )
            epub.writestr(
                f"OEBPS/c{i}.xhtml",
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
                f"<body><h1>Capitulo {i + 1}</h1>{body}</body></html>",
            )
    return path
