"""
Quick smoke tests for desktop_tool.
"""
import pytest


def test_desktop_tool_imports():
    """Verify desktop_tool module can be imported."""
    from backend.tools.desktop_tool import (
        mouse_kb_tool,
        file_tool as desktop_file_tool,
        document_tool as desktop_doc_tool,
        browser_tool as desktop_browser_tool,
        PYAUTOGUI_AVAILABLE,
        PIL_AVAILABLE,
    )
    # Just verify imports work
    assert mouse_kb_tool is not None
    assert desktop_file_tool is not None
    assert desktop_doc_tool is not None
    assert desktop_browser_tool is not None
    assert isinstance(PYAUTOGUI_AVAILABLE, bool)
    assert isinstance(PIL_AVAILABLE, bool)


def test_desktop_tool_classes():
    """Verify tool classes have expected methods."""
    from backend.tools.desktop_tool import (
        MouseKeyboardTool,
        FileManagementTool,
        DocumentTool,
        BrowserAutomationTool,
    )

    # Check MouseKeyboardTool has key methods
    assert hasattr(MouseKeyboardTool, 'move')
    assert hasattr(MouseKeyboardTool, 'click')
    assert hasattr(MouseKeyboardTool, 'type_text')

    # Check FileManagementTool
    assert hasattr(FileManagementTool, 'read_file')
    assert hasattr(FileManagementTool, 'save_file')
    assert hasattr(FileManagementTool, 'list_directory')

    # Check DocumentTool
    assert hasattr(DocumentTool, 'read_document')
    assert hasattr(DocumentTool, 'create_document')

    # Check BrowserAutomationTool
    assert hasattr(BrowserAutomationTool, 'browse_to')
    assert hasattr(BrowserAutomationTool, 'browser_screenshot')