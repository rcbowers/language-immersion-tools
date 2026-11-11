# Architectural Contract for Language Immersion Tools

## Introduction & Purpose

**This document is a binding architectural contract for all new features and code changes in the sentence miner application.**

**Before implementing ANY feature, you MUST read this document in full.** All new code must follow these rules. No exceptions. If existing code violates these patterns, you MUST refactor it BEFORE adding your feature (see Refactoring Mandate section).

---

## Layer Architecture

The codebase is organized into **four strict layers** with explicit dependency rules. Violations will be rejected.

### Layers

| Layer | Path | Purpose | Dependencies |
|-------|------|---------|--------------|
| **Core** | `src/immersion_app/core/` | Pure business logic, state managers, domain services | None (pure Python) |
| **GUI** | `src/immersion_app/gui/` | Presentation layer, widgets, windows, controllers | Core only |
| **Integrations** | `src/immersion_app/integrations/` | External service adapters (Anki, translation APIs, Whisper) | Core only |
| **Media** | `src/immersion_app/media/` | Parsing utilities (SRT, PDF extraction) | Core only |

### Core Layer (`src/immersion_app/core/`)

**Contains:**
- State managers (`mode.py`, `selection_state.py`)
- Domain services (`translation_service.py`, `anki_service.py`, `pdf_service.py`, `video_service.py`)
- Data models and domain logic

**Rules:**
- ❌ NO Qt GUI imports (`QWidget`, `QLabel`, etc.)
- ✓ QObject and Signal are allowed (for state management)
- ✓ Pure Python domain logic only
- ✓ No knowledge of widgets or UI

**Exemplar:** `src/immersion_app/core/mode.py`

### GUI Layer (`src/immersion_app/gui/`)

**Contains:**
- Widgets (`src/immersion_app/gui/widgets/`)
- Windows (`main_window.py`)
- Controllers (`src/immersion_app/gui/controllers/`)
- Theme system (`theme.py`)

**Rules:**
- ✓ Can import from Core layer
- ✓ Presentation logic only
- ❌ NO business logic in widgets
- ❌ NO direct service calls (use Controllers)

**Exemplar:** `src/immersion_app/gui/widgets/command_bar.py`

### Integrations Layer (`src/immersion_app/integrations/`)

**Contains:**
- Translation backend abstractions
- Anki integration
- Whisper/audio processing

**Rules:**
- ✓ Can use Core domain models
- ❌ NO GUI imports
- ✓ Abstractions for external services

### Media Layer (`src/immersion_app/media/`)

**Contains:**
- SRT parser
- PDF extraction helpers
- Media format utilities

**Rules:**
- ✓ Can use Core domain models
- ❌ NO GUI imports

### Dependency Flow

```
GUI ──────┐
          ├──> Core (domain logic, state)
Integrations ─┘
Media ────────┘

❌ Core CANNOT import from GUI, Integrations, or Media
❌ Integrations CANNOT import from GUI or Media
❌ Media CANNOT import from GUI or Integrations
```

---

## State Management Rules

### Critical Principle: Single Source of Truth

**Every piece of application state has exactly ONE owner.** State lives in the Core layer, never in widgets.

### State Managers

Current state managers:
- **`ModeManager`** (`src/immersion_app/core/mode.py`) - Owns workspace mode (WELCOME/PDF/VIDEO)
- **`SelectionState`** (`src/immersion_app/core/selection_state.py`) - Owns current word/sentence/translation and emits change signals
- **`ShortcutManager`** - Owns keyboard shortcut state

Current domain services:
- **`TranslationService`** - Owns translation cache, backend state, request deduplication, and async translation tasks
- **`AnkiService`** - Owns Anki connection state, queue workflows, and add/process operations
- **`PDFService`** - Owns PDF/EPUB document state (`doc_kind`, reflow layout for EPUB, TOC and chapter locations), render metadata, hit-testing helpers, and context extraction
- **`VideoService`** - Owns subtitle parsing state, subtitle offset state, and subtitle lookup helpers

### State Management Pattern

**Anti-pattern (NEVER do this):**
```python
# ❌ BAD: Widget storing domain state
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._current_mode = "pdf"  # State duplication!
        self._selected_word = None  # Duplicated state!
```

**Correct pattern:**
```python
# ✓ GOOD: Widget reads from state manager
class MyWidget(QWidget):
    def __init__(self, mode_manager: ModeManager):
        super().__init__()
        self.mode_manager = mode_manager
        self.mode_manager.mode_changed.connect(self._on_mode_changed)

    def _on_mode_changed(self, new_mode):
        # React to state changes
        self.update_display()
```

### State Change Flow

1. User interacts with widget
2. Widget emits signal (e.g., `word_clicked`)
3. Controller handles signal, updates state manager
4. State manager validates change, updates internal state
5. State manager emits `state_changed` signal
6. All listening widgets react to state change

**State flows DOWN from Core to GUI via signals. Never store state in widgets.**

---

## Communication Patterns

### When to Use Signals

Use signals for:
- ✓ Widget notifying parent of user action
- ✓ Async operations completing
- ✓ State changes propagating to multiple listeners
- ✓ Decoupling components that shouldn't know about each other

**Exemplar:** `src/immersion_app/gui/widgets/command_bar.py` - Emits `open_requested`, `close_requested`, `mode_changed` without knowing who handles them.

### When to Use Direct Method Calls

Use direct calls for:
- ✓ Parent configuring child widget display
- ✓ Simple getters for reading state
- ✓ Operations within same responsibility boundary

### Signal Naming Conventions

**Signals (past tense or request form):**
```python
# Events that happened
clicked = Signal()
changed = Signal()
loaded = Signal()

# Requests for action
open_requested = Signal()
close_requested = Signal()
translation_requested = Signal(str)
```

**Slots (private methods starting with `_on_` or `_handle_`):**
```python
def _on_word_clicked(self, word: str):
    """Handle word click event."""
    pass

def _handle_translation_ready(self, result: dict):
    """Handle translation completion."""
    pass
```

### Signal Connection Pattern

**Always organize signal connections in a dedicated method:**

```python
class MyWidget(QWidget):
    def __init__(self, mode_manager: ModeManager):
        super().__init__()
        self.mode_manager = mode_manager
        self._setup_ui()
        self._connect_signals()

    def _connect_signals(self):
        """Connect all signal-slot relationships."""
        self.mode_manager.mode_changed.connect(self._on_mode_changed)
        self.my_button.clicked.connect(self._on_button_clicked)
```

---

## Widget Design Contract

### Widget Responsibilities (ONLY These)

Widgets are **presentation components**. They:
- ✓ Render UI based on configuration
- ✓ Emit signals for user interactions
- ✓ Accept configuration via public methods
- ✓ Apply Theme styling

### Widgets MUST NOT

- ❌ Contain business logic
- ❌ Store domain state
- ❌ Call external services directly
- ❌ Know about other widgets (use signals)
- ❌ Make decisions about what happens next

### Example: Well-Designed Widget

See `src/immersion_app/gui/widgets/command_bar.py` as the template:

```python
class CommandBar(QWidget):
    """Command bar emits signals, doesn't execute logic."""

    # Signals for user actions
    open_requested = Signal()
    close_requested = Signal()
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def set_title(self, title: str, subtitle: str = ""):
        """Public API for display configuration."""
        self.title_widget.set_title(title, subtitle)

    def set_file_loaded(self, loaded: bool):
        """Public API for state-based display."""
        self.close_button.setVisible(loaded)
```

The widget **does not** open files, manage mode transitions, or know about the document. It emits signals and displays what it's told to display.

---

## Styling Rules

**ALL styling MUST go through the centralized Theme system.**

### Import and Usage

```python
from immersion_app.gui.theme import Theme

# Use Theme constants
self.setFixedHeight(Theme.COMMAND_BAR_HEIGHT)
self.setStyleSheet(f"background: {Theme.ACCENT};")

# Use Theme helpers
self.button.setStyleSheet(Theme.get_button_style("primary"))
self.label.setStyleSheet(Theme.get_label_style("heading"))
```

### Theme Reference (`src/immersion_app/gui/theme.py`)

**Colors:**
- `Theme.BG`, `Theme.SURFACE`, `Theme.SURFACE_ALT`
- `Theme.BORDER`, `Theme.BORDER_STRONG`
- `Theme.TEXT`, `Theme.TEXT_SOFT`, `Theme.TEXT_MUTED`
- `Theme.ACCENT`, `Theme.ACCENT_DARK`, `Theme.ACCENT_SOFT`

**Typography:**
- `Theme.FONT_FAMILY`, `Theme.FONT_FALLBACK`, `Theme.FONT_MONO`
- `Theme.FONT_SIZE_BODY`, `Theme.FONT_SIZE_HEADING`, `Theme.FONT_SIZE_CAPTION`
- `Theme.FONT_WEIGHT_REGULAR`, `Theme.FONT_WEIGHT_MEDIUM`, `Theme.FONT_WEIGHT_SEMIBOLD`

**Spacing:**
- `Theme.COMMAND_BAR_HEIGHT`, `Theme.TRANSPORT_BAR_HEIGHT`, `Theme.STATUS_BAR_HEIGHT`

**Helpers:**
- `Theme.get_button_style("primary" | "secondary" | "ghost")`
- `Theme.get_label_style("body" | "heading" | "caption" | "muted")`
- `Theme.get_input_style()`

### Anti-Patterns

```python
# ❌ BAD: Hardcoded values
self.setFixedHeight(56)
self.setStyleSheet("background: #5b6cff; color: #18181b;")
label.setFont(QFont("Inter", 14))

# ✓ GOOD: Theme constants
self.setFixedHeight(Theme.COMMAND_BAR_HEIGHT)
self.setStyleSheet(f"background: {Theme.ACCENT}; color: {Theme.TEXT};")
label.setStyleSheet(Theme.get_label_style("body"))
```

**NEVER use magic numbers, hardcoded hex colors, or inline font specifications.**

---

## Async Operations

All long-running operations (translation, Anki sync, file I/O) MUST run on background threads using the QRunnable worker pattern.

### QRunnable Worker Pattern

**Template:**

```python
from PySide6.QtCore import QRunnable, QObject, Signal, QThreadPool

class TranslationTask(QRunnable):
    """Async translation worker."""

    class Signals(QObject):
        finished = Signal(object)  # Result data
        error = Signal(str)        # Error message

    def __init__(self, text: str, backend):
        super().__init__()
        self.text = text
        self.backend = backend
        self.signals = self.Signals()

    def run(self):
        """Executed on background thread."""
        try:
            result = self.backend.translate(self.text)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

# Usage in window/controller
task = TranslationTask("こんにちは", self.translation_backend)
task.signals.finished.connect(self._on_translation_ready)
task.signals.error.connect(self._on_translation_error)
QThreadPool.globalInstance().start(task)
```

### Rules

- ✓ All I/O and network calls run on QThreadPool
- ✓ Emit signals on completion/error
- ✓ Never block the UI thread
- ❌ Never call `QApplication.processEvents()` as a hack

---

## Service Layer Pattern

**CRITICAL: Translation, Anki, PDF, and subtitle workflows belong in dedicated services.** New work must extend those services/controllers instead of reintroducing logic into `main_window.py`.

### Required Services (Current)

#### 1. TranslationService (`src/immersion_app/core/translation_service.py`)

**Responsibilities:**
- Own translation cache (dict of source → translation)
- Manage backend selection (online/offline toggle)
- Execute async translations via QRunnable workers
- Emit signals when translations complete

**Current API shape:**
```python
class TranslationService(QObject):
    translation_ready = Signal(int, str, str, bool)
    translation_failed = Signal(int, str, str, bool)
    batch_ready = Signal(list, list)
    batch_failed = Signal(str)
    mode_changed = Signal(str)

    def translate_async(self, text: str, *, visible: bool = True) -> int | None:
        """Start async translation and dedupe in-flight requests."""

    def prefetch_async(self, texts: list[str]) -> None:
        """Warm the translation cache for background words."""

    def set_mode(self, mode: str) -> None:
        """Switch between online/offline backends."""

    def set_languages(self, learning_language: str, native_language: str) -> None:
        """Reset cache and switch language pair."""

    def clear_cache(self) -> None:
        """Clear translation cache."""
```

#### 2. AnkiService (`src/immersion_app/core/anki_service.py`)

**Responsibilities:**
- Own Anki connection state (connected/disconnected)
- Manage offline queue for when Anki is unavailable
- Execute async card additions
- Fetch vocabulary lists

**Current API shape:**
```python
class AnkiService(QObject):
    status_check_started = Signal(int)
    connection_changed = Signal(bool)
    vocabulary_loaded = Signal(object)
    card_added = Signal(object)
    card_failed = Signal(str)
    queue_entry_added = Signal(object)
    queue_processed = Signal(int, int, str)

    def refresh_connection(self) -> None:
        """Check Anki availability in the background."""

    def add_card_now(self, sentence: str, word: str, translation: str) -> int:
        """Add a card when the UI already validated connectivity."""

    def queue_card(self, payload: dict) -> None:
        """Persist a queued card entry."""

    def process_queue_now(self) -> tuple[list[dict], list[dict]]:
        """Process queued cards and persist successes/failures."""
```

#### 3. PDFService (`src/immersion_app/core/pdf_service.py`)

**Responsibilities:**
- Handle PDF word extraction at click points
- Manage page rendering
- Provide sentence context for selected words

**Current API shape:**
```python
class PDFService(QObject):
    document_loaded = Signal(str, int)
    document_closed = Signal()

    def load_document(self, path: str):
        """Open a PDF and own the document lifecycle."""

    def render_page(self, page_index: int, zoom_factor: float):
        """Return render metadata used by the GUI to paint the page."""

    def word_at_point(self, word_order: list[tuple], x_pdf: float, y_pdf: float):
        """Hit-test a word at PDF coordinates."""

    def extract_context(self, selected_words: list[tuple], line_map: dict) -> str:
        """Get sentence/line context for a word span."""
```

#### 4. VideoService (`src/immersion_app/core/video_service.py`)

**Responsibilities:**
- Parse and manage subtitle files
- Handle subtitle offset adjustments
- Provide word context from subtitle lines

**Current API shape:**
```python
class VideoService(QObject):
    subtitles_loaded = Signal(int)
    subtitles_cleared = Signal()

    def load_subtitles(self, srt_path: str) -> None:
        """Load SRT file."""

    def subtitle_at_position(self, position_ms: int):
        """Get subtitle entry at the current media position."""

    def resolve_selection_range(...) -> tuple[list[int], tuple[int, int] | None]:
        """Resolve shift-selection in subtitle token ranges."""

    def set_offset(self, milliseconds: int) -> None:
        """Adjust subtitle timing offset."""
```

### Service Layer Rules

- ✓ Services live in `src/immersion_app/core/`
- ✓ Services extend QObject for signal support
- ✓ Services have NO GUI dependencies
- ✓ Services own domain state (cache, connection status)
- ✓ Services expose public APIs via methods
- ✓ Services communicate via signals
- ❌ Services NEVER import from GUI layer

---

## Controller Pattern

**Controllers orchestrate between Services and GUI.** They live in the GUI layer and handle workflows.

### Controllers Directory

```
src/immersion_app/gui/controllers/
├── __init__.py
├── pdf_controller.py
└── video_controller.py
```

Current implementation also includes `mining_controller.py` and `workspace_controller.py`.

### PDFController Example

**File:** `src/immersion_app/gui/controllers/pdf_controller.py`

**Responsibilities:**
- Connect PDF widget signals to services
- Update SelectionState when user clicks words
- Request translations via TranslationService
- Orchestrate PDF mode workflows

Additional controllers now in use:
- **`MiningController`** - Connects `SelectionState`, `TranslationService`, `AnkiService`, analytics, queue actions, and translation popover state
- **`VideoController`** - Owns subtitle/video orchestration, subtitle selection flow, and media-position-driven subtitle refresh
- **`WorkspaceController`** - Handles open/close/recent-file/session restore routing between the window and mode-specific controllers

```python
class PDFController(QObject):
    """Orchestrates PDF mode interactions."""

    def __init__(
        self,
        pdf_widget,
        pdf_service: PDFService,
        translation_service: TranslationService,
        selection_state: SelectionState
    ):
        super().__init__()
        self.pdf_widget = pdf_widget
        self.pdf_service = pdf_service
        self.translation_service = translation_service
        self.selection_state = selection_state
        self._connect_signals()

    def _connect_signals(self):
        self.pdf_widget.word_clicked.connect(self._on_word_clicked)
        self.translation_service.translation_ready.connect(self._on_translation_ready)

    def _on_word_clicked(self, word: str, page: int, index: int):
        """User clicked a word in PDF."""
        sentence = self.pdf_service.get_sentence_context(page, index)
        self.selection_state.set_selection(word, sentence)
        self.translation_service.translate_async(word)

    def _on_translation_ready(self, source: str, result: dict):
        """Translation completed."""
        self.selection_state.set_translation(result)
```

### Controller Rules

- ✓ Controllers live in `src/immersion_app/gui/controllers/`
- ✓ Controllers depend on Core services
- ✓ Controllers are thin orchestration layers
- ❌ Controllers do NOT contain business logic (that's in Services)
- ❌ Controllers do NOT render UI (that's in Widgets)

---

## Testing Requirements

**ALL new code MUST have tests.** No exceptions.

### State Managers: Pure Python Unit Tests

**Exemplar:** `tests/test_mode_manager.py`

```python
import unittest
from immersion_app.core.mode import ModeManager, WorkspaceMode

class TestModeManager(unittest.TestCase):
    def test_initial_state(self):
        manager = ModeManager()
        self.assertEqual(manager.current_mode, WorkspaceMode.WELCOME)

    def test_state_transition(self):
        manager = ModeManager()
        manager.set_pdf_loaded(True)
        self.assertTrue(manager.set_mode(WorkspaceMode.PDF))
        self.assertEqual(manager.current_mode, WorkspaceMode.PDF)
```

### Services: Mock External Dependencies

```python
import unittest
from unittest.mock import Mock, patch
from immersion_app.core.translation_service import TranslationService

class TestTranslationService(unittest.TestCase):
    def test_cache_hit(self):
        service = TranslationService()
        service._cache["hello"] = {"translation": "こんにちは"}

        # Should not call backend on cache hit
        with patch.object(service, '_backend') as mock_backend:
            service.translate_async("hello")
            mock_backend.translate.assert_not_called()
```

### Widgets: Test Signal Emission

Use `pytest-qt` for widget tests:

```python
def test_command_bar_emits_open_signal(qtbot):
    bar = CommandBar()
    qtbot.addWidget(bar)

    with qtbot.waitSignal(bar.open_requested, timeout=1000):
        bar.open_button.click()
```

### Controllers: Integration Tests

Mock services, test orchestration:

```python
def test_pdf_controller_updates_selection_on_click():
    mock_pdf_service = Mock()
    mock_selection_state = Mock()
    controller = PDFController(widget, mock_pdf_service, ..., mock_selection_state)

    controller._on_word_clicked("猫", page=1, index=42)

    mock_selection_state.set_selection.assert_called_once()
```

### Test Organization

```
tests/
├── core/              # Service and state manager tests
│   ├── test_mode_manager.py
│   ├── test_translation_service.py
│   └── test_anki_service.py
├── gui/               # Widget and controller tests
│   ├── test_command_bar.py
│   └── test_pdf_controller.py
└── test_subtitle_widget.py
```

---

## Refactoring Mandate

**CRITICAL RULE: Before adding ANY new feature, you MUST refactor the related code first.**

This is not optional. Technical debt accumulation stops here.

### Mandatory Workflow

1. **Identify the feature request**
   - Example: "Add caching to translations"

2. **Locate related code in `main_window.py`**
   - Find translation logic currently in `main_window.py`

3. **Extract to Service layer FIRST**
   - Create `src/immersion_app/core/translation_service.py`
   - Move translation logic from `main_window.py` → `TranslationService`
   - Write tests for the service

4. **Create/Update Controller**
   - Create or update appropriate controller
   - Move orchestration from `main_window.py` → Controller

5. **Add tests for extracted code**
   - Unit tests for service
   - Integration tests for controller

6. **THEN implement your feature**
   - Now add caching to the clean `TranslationService`
   - Follow proper architecture from the start

### Example Refactoring Sequence

**Bad (immediate feature addition):**
```python
# ❌ Adding feature to already-messy main_window.py
class MainWindow(QMainWindow):
    def translate_word(self, word):
        # 50 lines of existing messy logic
        # + 20 more lines for new cache feature
        # = 70 lines of unmaintainable code
```

**Good (refactor first):**
```python
# ✓ Step 1: Extract service
class TranslationService(QObject):
    def translate_async(self, word):
        # Clean, tested translation logic

# ✓ Step 2: Create controller
class TranslationController(QObject):
    def __init__(self, service, selection_state):
        self.service = service
        # Orchestration only

# ✓ Step 3: NOW add cache to clean service
class TranslationService(QObject):
    def __init__(self):
        self._cache = {}  # New feature in right place
```

### Enforcement

If you are asked to add a feature and the related code is in `main_window.py`:

1. **STOP**
2. **Propose refactoring plan to user**
3. **Extract service/controller first**
4. **Get approval to proceed**
5. **THEN implement feature**

**Do NOT add features to messy code. Refactor FIRST.**

---

## File Organization

### Naming Conventions

**State Managers:**
- Pattern: `*_manager.py` or `*_state.py`
- Location: `src/immersion_app/core/`
- Examples: `mode_manager.py`, `selection_state.py`

**Services:**
- Pattern: `*_service.py`
- Location: `src/immersion_app/core/`
- Examples: `translation_service.py`, `anki_service.py`, `pdf_service.py`

**Controllers:**
- Pattern: `*_controller.py`
- Location: `src/immersion_app/gui/controllers/`
- Examples: `pdf_controller.py`, `video_controller.py`

**Widgets:**
- Descriptive names
- Location: `src/immersion_app/gui/widgets/`
- Examples: `command_bar.py`, `subtitle_widget.py`

### Directory Structure

```
src/immersion_app/
├── core/                      # Domain layer (no GUI)
│   ├── mode.py               ✓ Exemplar state manager
│   ├── selection_state.py    ✓ Exemplar state manager
│   ├── translation_service.py  (to be created)
│   ├── anki_service.py         (to be created)
│   ├── pdf_service.py          (to be created)
│   └── video_service.py        (to be created)
├── gui/                       # Presentation layer
│   ├── theme.py              ✓ Exemplar design system
│   ├── main_window.py        ⚠ Needs decomposition
│   ├── controllers/            (to be created)
│   │   ├── __init__.py
│   │   ├── pdf_controller.py
│   │   └── video_controller.py
│   └── widgets/
│       └── command_bar.py    ✓ Exemplar widget
├── integrations/              # External services
│   ├── translation_backends.py
│   └── anki/
└── media/                     # Parsing utilities
    └── srt_parser.py

tests/
├── core/                      (to be created)
│   ├── test_translation_service.py
│   └── test_anki_service.py
├── gui/                       (to be created)
│   ├── test_pdf_controller.py
│   └── test_video_controller.py
└── test_mode_manager.py      ✓ Exemplar test
```

---

### Current Directory Snapshot

```text
src/immersion_app/
|-- core/
|   |-- mode.py
|   |-- selection_state.py
|   |-- translation_service.py
|   |-- anki_service.py
|   |-- pdf_service.py
|   `-- video_service.py
|-- gui/
|   |-- theme.py
|   |-- main_window.py
|   |-- controllers/
|   |   |-- __init__.py
|   |   |-- mining_controller.py
|   |   |-- pdf_controller.py
|   |   |-- video_controller.py
|   |   `-- workspace_controller.py
|   `-- widgets/
|       |-- command_bar.py
|       |-- pdf_clickable_label.py
|       |-- queue_dialog.py
|       `-- subtitle_generator_dialog.py
|-- integrations/
|   `-- translation_backends.py
`-- media/
    `-- subtitle_parser.py

tests/
|-- test_mode_manager.py
|-- test_selection_state.py
|-- test_anki_service.py
|-- test_translation_service.py
|-- test_pdf_controller.py
|-- test_video_service.py
|-- test_pdf_ui.py
`-- test_subtitle_widget.py
```

This snapshot supersedes the older "to be created" examples above.

---

## Critical Anti-Patterns

**NEVER do these:**

1. ❌ **Mix business logic in widget event handlers**
   ```python
   # BAD
   def on_button_clicked(self):
       result = api.call()  # Business logic in widget!
       self.process(result)
   ```

2. ❌ **Hardcode colors, sizes, or magic numbers**
   ```python
   # BAD
   self.setFixedHeight(56)
   self.setStyleSheet("background: #5b6cff;")
   ```

3. ❌ **Store state in widgets**
   ```python
   # BAD
   class MyWidget(QWidget):
       def __init__(self):
           self._current_mode = "pdf"  # Duplicated state!
   ```

4. ❌ **Use direct widget-to-widget communication**
   ```python
   # BAD
   class WidgetA(QWidget):
       def do_thing(self):
           self.parent().widget_b.update()  # Tight coupling!
   ```

5. ❌ **Block UI thread with synchronous operations**
   ```python
   # BAD
   def translate(self):
       result = requests.get(url).json()  # Blocking call!
       self.display(result)
   ```

6. ❌ **Duplicate state across objects**
   ```python
   # BAD: Same state in multiple places
   self.current_word = "猫"
   self.selection_state._word = "猫"  # Duplication!
   ```

7. ❌ **Add features without refactoring first**
   ```python
   # BAD: Piling features onto messy code
   class MainWindow(QMainWindow):
       def massive_method_with_everything(self):
           # 200 lines of mixed concerns
           # + your new feature
           # = unmaintainable
   ```

---

## Quick Reference Checklist

**Before implementing ANY feature, verify:**

- [ ] I have read this entire `agents.md` document
- [ ] I identified related code in `main_window.py` or elsewhere
- [ ] I extracted services and added tests FIRST (if needed)
- [ ] My design uses proper layers (Core/GUI/Integrations/Media)
- [ ] State lives in state managers (Core layer)
- [ ] Widgets are pure presentation (no business logic)
- [ ] I use signals for decoupled communication
- [ ] I use Theme for ALL styling (no hardcoded values)
- [ ] Async operations use QRunnable workers
- [ ] I wrote comprehensive tests
- [ ] I updated this document if I discovered new patterns

---

## Exemplar Files Reference

**Study these files as templates:**

- **State Manager:** `src/immersion_app/core/mode.py`
  - Perfect state management pattern
  - Validation, signals, single source of truth

- **Theme System:** `src/immersion_app/gui/theme.py`
  - Centralized design tokens
  - Styling helpers
  - No magic numbers

- **Widget Design:** `src/immersion_app/gui/widgets/command_bar.py`
  - Signal-based communication
  - No business logic
  - Theme usage
  - Clean separation of concerns

- **Testing Pattern:** `tests/test_mode_manager.py`
  - Pure Python unit tests
  - Signal capturing
  - State transition testing

**Active Refactor Target:**
- `src/immersion_app/gui/main_window.py`
  - Core workflows have been extracted to services/controllers
  - The file still contains compatibility wrappers and some window-level orchestration
  - New feature work should go into services/controllers/widgets first, then delete wrappers from the window as coverage moves

---

## Enforcement

This is a binding contract. All new code must follow these rules.

If you are implementing a feature and existing code violates these patterns:
1. **STOP**
2. **Refactor the existing code first**
3. **Add tests**
4. **THEN implement your feature**

**Refactoring is not optional. It is mandatory.**

The time for "quick hacks" is over. Every new feature is an opportunity to improve the architecture.

---

*This document is a living contract. Update it when you discover new patterns or architectural decisions.*
