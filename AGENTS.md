# Quick-Start Agent Guide

This codebase is for LinguaLoop, a custom-written app for active immersion in foreign language content and mining unknown words into Anki cards.

## ⚠ Binding Contract

The file `architecture_design_readme.md` (897 lines) is a **binding architectural contract**. All code changes MUST follow its rules. This guide provides quick reference to the most critical patterns.

---

## 🏗 Quick Architecture Reference

### 4-Layer Dependency Rules

```
┌─────────────────┐
│   GUI Layer     │ ──┐
│ (Widgets, UI)   │   │
└─────────────────┘   │
                      ├──> Core Layer (State, Services)
┌─────────────────┐   │     • NO Qt GUI imports
│ Integrations    │ ──┤     • Pure business logic
│ (Anki, APIs)    │   │     • Single source of truth
└─────────────────┘   │
                      │
┌─────────────────┐   │
│   Media Layer   │ ──┘
│ (Parsers, SRT)  │
└─────────────────┘

```

### What Goes Where

| Layer | Path | Contains | Can Import | CANNOT Have |
|-------|------|----------|------------|-------------|
| **Core** | `src/immersion_app/core/` | State managers, services, domain logic | Pure Python, QObject/Signal only | ❌ QWidget, QLabel, any GUI |
| **GUI** | `src/immersion_app/gui/` | Widgets, windows, controllers, theme | Core layer | ❌ Business logic, direct service calls |
| **Integrations** | `src/immersion_app/integrations/` | External APIs (Anki, translation) | Core models | ❌ GUI imports |
| **Media** | `src/immersion_app/media/` | Parsers (SRT, PDF utils) | Core models | ❌ GUI imports |

**Reference:** `architecture_design_readme.md` lines 11-89

---

## ✅ Critical Rules Checklist

### State Management

- [ ] State lives in Core layer state managers (NOT in widgets)
- [ ] State managers emit signals when state changes
- [ ] Widgets listen to state changes, never store state
- [ ] Single source of truth for every piece of data

**Anti-pattern:**
```python
# ❌ BAD: Widget storing state
class MyWidget(QWidget):
    def __init__(self):
        self._current_mode = "pdf"  # State duplication!
```

**Correct pattern:**
```python
# ✓ GOOD: Widget reads from state manager
class MyWidget(QWidget):
    def __init__(self, mode_manager: ModeManager):
        self.mode_manager = mode_manager
        self.mode_manager.mode_changed.connect(self._on_mode_changed)
```

**Reference:** `architecture_design_readme.md` lines 93-146

### Widget Design

- [ ] Widgets are pure presentation (no business logic)
- [ ] Widgets emit signals for user actions
- [ ] Widgets expose public methods for display configuration
- [ ] Widgets use Theme for ALL styling (no hardcoded values)
- [ ] Widgets don't know about other widgets (use signals)

**Reference:** `architecture_design_readme.md` lines 215-260

### Styling (Theme System)

- [ ] ALL colors come from `Theme` constants
- [ ] ALL fonts use `Theme.FONT_*` constants
- [ ] ALL spacing uses `Theme.*_HEIGHT` or `Theme.*_WIDTH`
- [ ] Use `Theme.get_button_style()` for buttons
- [ ] Use `Theme.get_label_style()` for labels

### Async Operations

- [ ] All I/O and network calls use QRunnable workers
- [ ] Workers emit signals on completion/error
- [ ] Never block UI thread
- [ ] Never call `QApplication.processEvents()`

**Reference:** `architecture_design_readme.md` lines 320-365

### Testing

- [ ] ALL new code has tests
- [ ] State managers: pure Python unit tests
- [ ] Services: mock external dependencies
- [ ] Widgets: test signal emission (use pytest-qt)
- [ ] Controllers: integration tests with mocked services

**Reference:** `architecture_design_readme.md` lines 545-627

---

## 📚 Exemplar Files (Study These First)

Before implementing similar functionality, study these exemplar files:

| What You're Building | Study This File | What It Demonstrates |
|---------------------|-----------------|---------------------|
| State manager | `src/immersion_app/core/mode.py` | Perfect state management, validation, signals |
| Widget | `src/immersion_app/gui/widgets/command_bar.py` | Signal-based communication, no business logic |
| Theme/styling | `src/immersion_app/gui/theme.py` | Centralized design tokens, no magic numbers |
| Tests | `tests/test_mode_manager.py` | Unit testing, signal capture, state transitions |

### ⚠ Problem File (Do NOT Add Features Here)

**`src/immersion_app/gui/main_window.py`** (~1900 lines)
- Currently contains business logic that should be in services
- Extract services BEFORE adding features
- Move orchestration to controllers
- Keep only window-level UI logic

**Reference:** `architecture_design_readme.md` lines 849-878

---

## 🚫 Services That DON'T Exist Yet

**CRITICAL: These services need to be extracted from `main_window.py` before use.**

The following services are **planned but not implemented**:

- ❌ `TranslationService` - Extract translation logic first
- ❌ `AnkiService` - Extract Anki logic first
- ❌ `PDFService` - Extract PDF logic first
- ❌ `VideoService` - Extract video logic first

**If your feature needs one of these:**

1. Extract the service from `main_window.py` FIRST
2. Write tests for the service
3. Create controller if needed
4. THEN add your feature

**Reference:** `architecture_design_readme.md` lines 367-477

---

## 🔄 Implementation Workflow

### Standard Feature Addition

1. **Understand existing code**
   - Read related files
   - Check if pattern exists in exemplar files

2. **Check refactoring requirement**
   - Is related code in `main_window.py`? → Extract first
   - Does state manager exist? → Create if needed
   - Does service exist? → Extract if needed

3. **Design approach**
   - Identify correct layer
   - Plan signal flow
   - Plan state management

4. **Implement with tests**
   - Write service/state manager (Core layer)
   - Write tests for service/state manager
   - Create/update controller (GUI layer)
   - Create/update widget (GUI layer)
   - Write integration tests

5. **Verify**
   - All tests pass
   - Layer boundaries respected
   - No hardcoded styling
   - Signals used correctly

### Refactoring-First Workflow

**When feature requires refactoring:**

1. **Propose refactoring plan** to user
   - "Before adding X, I need to extract Y service from main_window.py"

2. **Extract service**
   - Create `src/immersion_app/core/Y_service.py`
   - Move logic from `main_window.py`
   - Keep NO GUI dependencies

3. **Write service tests**
   - Unit tests in `tests/core/test_Y_service.py`

4. **Create controller**
   - Create `src/immersion_app/gui/controllers/Y_controller.py`
   - Move orchestration from `main_window.py`

5. **Write controller tests**
   - Integration tests in `tests/gui/test_Y_controller.py`

6. **Get approval**

7. **THEN implement feature**
   - Now add feature to clean architecture

**Reference:** `architecture_design_readme.md` lines 630-704

---

## 📁 File Naming Conventions

### Where Files Belong

```
src/immersion_app/
├── core/
│   ├── *_manager.py         # State managers (mode_manager.py)
│   ├── *_state.py           # State managers (selection_state.py)
│   └── *_service.py         # Domain services (translation_service.py)
│
├── gui/
│   ├── theme.py             # Design system (ONLY ONE)
│   ├── main_window.py       # Main window (decompose this)
│   ├── controllers/
│   │   └── *_controller.py  # Orchestration (pdf_controller.py)
│   └── widgets/
│       └── *.py             # Presentation (command_bar.py)
│
├── integrations/
│   └── *_backends.py        # External APIs (translation_backends.py)
│
└── media/
    └── *_parser.py          # Parsing utilities (subtitle_parser.py)

tests/
├── core/
│   └── test_*.py            # Service and state tests
└── gui/
    └── test_*.py            # Widget and controller tests
```

**Reference:** `architecture_design_readme.md` lines 707-765

---

## 📊 Current Architecture State

### ✅ What Exists (Can Use Immediately)

**Core Layer:**
- ✅ `ModeManager` - Workspace mode state (WELCOME/PDF/VIDEO)
- ✅ `SelectionState` - Current word/sentence/translation
- ✅ `ShortcutManager` - Keyboard shortcuts

**GUI Layer:**
- ✅ `Theme` - Complete design system
- ✅ `CommandBar` - Top bar widget
- ✅ `TranslationPopover` - Translation display
- ✅ `PDFStatusBar` - Status bar widget
- ✅ `TransportBar` - Media controls
- ✅ Other widgets in `src/immersion_app/gui/widgets/`

**Integrations Layer:**
- ✅ Translation backends (online/offline)
- ✅ Anki integration functions

**Media Layer:**
- ✅ SRT parser
- ✅ Subtitle matching utilities

### ⚠ What Needs Extraction (Doesn't Exist Yet)

**Services that need extraction from `main_window.py`:**
- ❌ `TranslationService` - Translation logic, cache, backend management
- ❌ `AnkiService` - Anki connection, card queue, vocabulary fetch
- ❌ `PDFService` - PDF rendering, word extraction, context
- ❌ `VideoService` - Subtitle management, timing, context

**Controllers that need creation:**
- ❌ `PDFController` - PDF mode orchestration
- ❌ `VideoController` - Video mode orchestration

### 🏗 Directory Structure Status

```
src/immersion_app/
├── core/
│   ├── mode.py                  ✅ Exemplar state manager
│   ├── selection_state.py       ✅ Exemplar state manager
│   ├── shortcuts.py             ✅ Shortcut manager
│   ├── translation_service.py   ❌ TO BE CREATED
│   ├── anki_service.py          ❌ TO BE CREATED
│   ├── pdf_service.py           ❌ TO BE CREATED
│   └── video_service.py         ❌ TO BE CREATED
│
├── gui/
│   ├── theme.py                 ✅ Exemplar design system
│   ├── main_window.py           ⚠ NEEDS DECOMPOSITION (~1900 lines)
│   ├── controllers/             ❌ DIRECTORY DOESN'T EXIST
│   │   ├── __init__.py          ❌ TO BE CREATED
│   │   ├── pdf_controller.py    ❌ TO BE CREATED
│   │   └── video_controller.py  ❌ TO BE CREATED
│   └── widgets/
│       ├── command_bar.py       ✅ Exemplar widget
│       └── ...                  ✅ Other widgets
│
└── integrations/
    └── translation_backends.py  ✅ Exists

tests/
├── core/                        ❌ DIRECTORY DOESN'T EXIST
│   ├── test_translation_service.py  ❌ TO BE CREATED
│   └── test_anki_service.py         ❌ TO BE CREATED
├── gui/                         ❌ DIRECTORY DOESN'T EXIST
│   ├── test_pdf_controller.py       ❌ TO BE CREATED
│   └── test_video_controller.py     ❌ TO BE CREATED
└── test_mode_manager.py         ✅ Exemplar test pattern
```

---

## 📝 Post-Implementation

After implementing features:

- [ ] Update this document if you discovered new patterns
- [ ] Add entry to `changelog.md`
- [ ] Ensure tests are passing
- [ ] Update `architecture_design_readme.md` if architectural decisions were made

---

## 💡 Key Takeaways

1. **Refactor FIRST, then add features** - Not optional
2. **State lives in Core layer** - Never in widgets
3. **Widgets are dumb** - Signals only, no business logic
4. **Use Theme for everything** - No magic numbers
5. **Test everything** - No exceptions
6. **Study exemplar files** - Don't guess patterns
7. **Extract from main_window.py** - Before adding related features
8. **Controllers don't exist yet** - Create them as you extract services

---

*This is a living document. Update it when you discover new patterns or commonly needed guidance.*