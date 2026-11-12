# PyInstaller spec: one-folder, windowed build of Language Immersion Tools.
# Build with:  pyinstaller packaging/immersion.spec --noconfirm
# Only the core app is frozen. Offline translation (torch) and subtitle
# generation (Whisper) are source-install extras and are excluded on purpose.
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

datas = [
    (str(SRC / "immersion_app" / "gui" / "fonts"), "immersion_app/gui/fonts"),
    (str(ROOT / "LICENSE"), "."),
]
icon = ROOT / "packaging" / "icon.ico"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=["googletrans", "httpx", "h2", "hyperframe", "hpack"],
    excludes=[
        "torch", "transformers", "whisper", "sentencepiece", "sacremoses",
        "matplotlib", "spacy", "tkinter", "pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LanguageImmersionTools",
    console=False,
    icon=str(icon) if icon.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LanguageImmersionTools")
