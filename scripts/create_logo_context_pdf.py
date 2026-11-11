"""Create a self-contained visual brief for generating a Language Immersion Tools logo.

Run from the repository root with the project virtual environment:
    .venv\\Scripts\\python.exe scripts\\create_logo_context_pdf.py
"""

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPdfWriter, QTextOption
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtGui import QGuiApplication


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "LanguageImmersionTools_logo_context.pdf"
SHOTS = ROOT / "docs" / "screenshots"

# Palette sampled from the app's actual Theme class.
INK = QColor("#18181b")
SOFT = QColor("#52525b")
MUTED = QColor("#71717a")
PAPER = QColor("#fafafa")
SURFACE = QColor("#ffffff")
ALT = QColor("#f4f4f5")
ACCENT = QColor("#5b6cff")
ACCENT_DARK = QColor("#2f3fd9")
LINE = QColor("#e4e4e7")
DARK = QColor("#111318")
WHITE = QColor("#f3f4f6")


class Brief:
    def __init__(self):
        font_dir = ROOT / "src" / "immersion_app" / "gui" / "fonts"
        QFontDatabase.addApplicationFont(str(font_dir / "Inter-Regular.ttf"))
        QFontDatabase.addApplicationFont(str(font_dir / "Inter-SemiBold.ttf"))
        QFontDatabase.addApplicationFont(str(font_dir / "Inter-Bold.ttf"))
        self.writer = QPdfWriter(str(OUTPUT))
        self.writer.setResolution(144)
        self.writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        self.writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        self.painter = QPainter(self.writer)
        self.w = self.writer.width()
        self.h = self.writer.height()
        self.m = 108
        self.page_no = 0

    def font(self, size, weight=QFont.Weight.Normal):
        f = QFont("Inter")
        f.setPointSizeF(size)
        f.setWeight(weight)
        return f

    def box(self, x, y, w, h, fill, radius=0, pen=None):
        self.painter.save()
        self.painter.setBrush(fill)
        self.painter.setPen(pen if pen else Qt.PenStyle.NoPen)
        self.painter.drawRoundedRect(QRectF(x, y, w, h), radius, radius)
        self.painter.restore()

    def rule(self, x1, y1, x2, y2, color=LINE, width=1):
        self.painter.save()
        pen = self.painter.pen()
        pen.setColor(color)
        pen.setWidth(width)
        self.painter.setPen(pen)
        self.painter.drawLine(x1, y1, x2, y2)
        self.painter.restore()

    def text(self, value, x, y, w, h, size=11, color=INK, weight=QFont.Weight.Normal,
             align=Qt.AlignmentFlag.AlignLeft, leading=1.32):
        self.painter.save()
        self.painter.setFont(self.font(size, weight))
        self.painter.setPen(color)
        option = QTextOption(align | Qt.AlignmentFlag.AlignTop)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        self.painter.drawText(QRectF(x, y, w, h), value, option)
        self.painter.restore()

    def label(self, value, x, y, w=300, dark=False):
        self.text(value.upper(), x, y, w, 28, 7.3, WHITE if dark else ACCENT,
                  QFont.Weight.DemiBold)

    def title(self, value, x, y, w, dark=False, size=26):
        # Leave room for wrapped two-line headings at the document's print DPI.
        self.text(value, x, y, w, 140, size, WHITE if dark else INK, QFont.Weight.Bold)

    def footer(self):
        self.rule(self.m, self.h - 74, self.w - self.m, self.h - 74)
        self.text("LANGUAGE IMMERSION TOOLS  /  LOGO GENERATION CONTEXT", self.m, self.h - 56,
                  420, 22, 7, MUTED, QFont.Weight.DemiBold)
        self.text(f"{self.page_no:02d}", self.w - self.m - 40, self.h - 56,
                  40, 22, 7, MUTED, QFont.Weight.DemiBold,
                  Qt.AlignmentFlag.AlignRight)

    def page(self, dark=False):
        if self.page_no:
            self.writer.newPage()
        self.page_no += 1
        self.painter.fillRect(0, 0, self.w, self.h, DARK if dark else PAPER)

    def image(self, filename, x, y, w, h, caption=None):
        image = QImage(str(SHOTS / filename))
        if image.isNull():
            raise RuntimeError(f"Cannot read {filename}")
        self.box(x - 3, y - 3, w + 6, h + 6, SURFACE, 5, LINE)
        scaled = image.scaled(int(w), int(h), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        dx = x + (w - scaled.width()) / 2
        dy = y + (h - scaled.height()) / 2
        self.painter.drawImage(QRectF(dx, dy, scaled.width(), scaled.height()), scaled)
        if caption:
            self.text(caption, x, y + h + 15, w, 36, 8.2, MUTED)

    def chip(self, value, x, y, w):
        self.box(x, y, w, 34, QColor("#e9ecff"), 17)
        self.text(value, x, y + 8, w, 18, 8.4, ACCENT_DARK, QFont.Weight.DemiBold,
                  Qt.AlignmentFlag.AlignHCenter)

    def draw(self):
        # Cover
        self.page()
        self.box(0, 0, self.w, 20, ACCENT)
        self.label("Visual brief / use as image-generation context", self.m, 130)
        self.title("Language Immersion Tools\nlogo context", self.m, 172, self.w - 2 * self.m, size=35)
        self.text("A focused desktop workspace for active language immersion: read or watch real content, look up unfamiliar language in place, and turn meaningful examples into Anki cards.",
                  self.m, 345, self.w - 2 * self.m, 105, 16, SOFT, QFont.Weight.Normal)
        self.box(self.m, 505, self.w - 2 * self.m, 220, SURFACE, 18, LINE)
        self.label("The feeling", self.m + 34, 542)
        self.text("Quietly capable • focused • modern • personal • fluent", self.m + 34, 578,
                  self.w - 2 * self.m - 68, 38, 17, INK, QFont.Weight.DemiBold)
        self.text("The product removes the friction between noticing a word and learning it. The identity should feel like a smooth connection or loop—not like a generic translation app, classroom software, or a flashcard mascot.",
                  self.m + 34, 633, self.w - 2 * self.m - 68, 68, 10.5, SOFT)
        self.label("Included", self.m, 800)
        self.text("Product description • app UI references • visual language • logo brief • paste-ready generation prompt",
                  self.m, 834, self.w - 2 * self.m, 38, 9.5, SOFT)
        self.footer()

        # Product + audience
        self.page()
        self.label("01 / Product at a glance", self.m, 92)
        self.title("Active immersion,\nwithout breaking focus.", self.m, 128, 680, size=27)
        self.text("Language Immersion Tools is a free cross-platform desktop app for people learning languages through books, PDFs/EPUBs, films, and shows. It supports Spanish, French, Italian, Japanese, Chinese, and English in any combination.",
                  self.m, 284, self.w - 2 * self.m, 80, 11.2, SOFT)
        self.label("Core loop", self.m, 405)
        items = [
            ("01", "Immerse", "Open a book, PDF/EPUB, or subtitled video."),
            ("02", "Understand", "Click a word or phrase for an in-context translation."),
            ("03", "Remember", "Create or queue a rich Anki card in one keystroke."),
        ]
        colw = (self.w - 2 * self.m - 36) / 3
        for i, (num, heading, body) in enumerate(items):
            x = self.m + i * (colw + 18)
            self.box(x, 449, colw, 174, SURFACE, 13, LINE)
            self.text(num, x + 20, 473, 50, 28, 9, ACCENT, QFont.Weight.Bold)
            self.text(heading, x + 20, 513, colw - 40, 30, 15, INK, QFont.Weight.Bold)
            self.text(body, x + 20, 554, colw - 40, 55, 9.2, SOFT)
        self.label("Audience", self.m, 684)
        self.text("Self-directed language learners who value real media, durable recall, and a minimal workflow. They are often familiar with Anki and sentence mining, and want tools that stay out of the way while they read or watch.",
                  self.m, 718, self.w - 2 * self.m, 65, 10.5, SOFT)
        self.label("Personality", self.m, 820)
        for i, word in enumerate(["Focused", "Human", "Precise", "Progressive"]):
            self.chip(word, self.m + i * 155, 854, 137)
        self.footer()

        # Reader context
        self.page()
        self.label("02 / The main moment", self.m, 92)
        self.title("The reader is the product’s center of gravity.", self.m, 128, self.w - 2 * self.m, size=25)
        self.text("A selected word becomes an unobtrusive translation popover with an immediate “add to Anki” action. The logo should belong in this composed, content-first environment.",
                  self.m, 250, self.w - 2 * self.m, 50, 10.7, SOFT)
        self.image("reader.png", self.m, 332, self.w - 2 * self.m, 515,
                   "Light workspace: document page, compact command bar, indigo selection accents, and a restrained translation card.")
        self.footer()

        # Gallery
        self.page()
        self.label("03 / Supporting app views", self.m, 92)
        self.title("A product with a calm,\norganized workspace.", self.m, 128, 610, size=25)
        self.text("The interface favors clear hierarchy, generous white space, neutral surfaces, rounded cards, and a small indigo accent. It is useful and polished rather than playful or academic.",
                  self.m, 279, self.w - 2 * self.m, 52, 10.7, SOFT)
        self.image("welcome.png", self.m, 365, 735, 460,
                   "Welcome view: recent sources and a clean library-like starting point.")
        self.image("settings.png", 878, 365, 290, 380,
                   "Settings: practical, configurable, understated.")
        self.footer()

        # Visual system and dark mode
        self.page(dark=True)
        self.label("04 / Visual language", self.m, 92, dark=True)
        self.title("A loop of attention,\nmeaning, and memory.", self.m, 128, 680, dark=True, size=27)
        self.text("The identity may use the idea of a loop, a connective path, a passage from source text to understanding, or a subtle card/page cue. Keep the result simple enough to work as a small app icon.",
                  self.m, 284, self.w - 2 * self.m, 65, 11.2, QColor("#c3cad5"))
        self.label("UI palette", self.m, 395, dark=True)
        colors = [("#5B6CFF", ACCENT), ("#111318", DARK), ("#181B22", QColor("#181b22")),
                  ("#F3F4F6", WHITE)]
        for i, (name, color) in enumerate(colors):
            x = self.m + i * 215
            self.box(x, 438, 180, 72, color, 12, QColor("#343946"))
            self.text(name, x, 526, 180, 25, 8.5, QColor("#c3cad5"), QFont.Weight.DemiBold,
                      Qt.AlignmentFlag.AlignHCenter)
        self.image("reader_dark.png", self.m, 594, self.w - 2 * self.m, 290,
                   "Dark mode preserves the same restrained layout, cool neutrals, and luminous indigo accent.")
        self.footer()

        # Prompt page
        self.page()
        self.label("05 / Direction for a logo generator", self.m, 92)
        self.title("Generate a distinctive\nmark, not a stock language icon.", self.m, 128, 740, size=25)
        self.label("Desired logo", self.m, 286)
        prompt = (
            "Create a logo for Language Immersion Tools, a desktop app for active language immersion and Anki sentence mining. "
            "The app lets learners read books or watch subtitled video, click unfamiliar words for translations, "
            "and save meaningful sentence examples to Anki without leaving their content.\n\n"
            "Design a refined, minimal icon plus wordmark. Express an elegant loop of attention → meaning → memory, "
            "perhaps through a continuous path, a subtle linked-page/card motif, or an abstract letterform. It should feel "
            "focused, modern, quietly intelligent, and personal: a tool for serious self-directed learners, not a school app. "
            "Use a cool indigo accent (#5B6CFF) with charcoal/soft-neutral companions. The mark must be legible at favicon "
            "and desktop-app-icon sizes, work in one color, and be equally credible in light and dark mode. Use clean geometric "
            "forms with gentle rounding and ample negative space.\n\n"
            "Avoid: flags, globes, speech bubbles, owls, graduation caps, generic book stacks, obvious infinity symbols, "
            "cartoon mascots, busy gradients, or anything that looks like a generic translation or flashcard app."
        )
        self.box(self.m, 326, self.w - 2 * self.m, 390, SURFACE, 16, LINE)
        self.text(prompt, self.m + 32, 360, self.w - 2 * self.m - 64, 320, 10.3, SOFT)
        self.label("Delivery asks", self.m, 765)
        self.text("• Icon + horizontal wordmark  • Light and dark lockups  • Single-color version  • SVG-ready vector forms  • No mockup-only presentation",
                  self.m, 800, self.w - 2 * self.m, 38, 10.2, SOFT)
        self.text("Reference only: screens in this document describe the current product UI. Do not replicate UI screenshots or use the existing logo as a design constraint.",
                  self.m, 864, self.w - 2 * self.m, 30, 8.5, MUTED)
        self.footer()

        self.painter.end()


if __name__ == "__main__":
    # Qt's font and PDF paint engines expect an application instance even though
    # this command has no visible UI.
    application = QGuiApplication([])
    brief = Brief()
    brief.draw()
    print(f"Created {OUTPUT}")
