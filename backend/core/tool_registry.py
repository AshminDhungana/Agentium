"""
Tool Registry
"""
import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.tools.nodriver_tool import nodriver_tool
from backend.tools.browser_tool  import BrowserTool
from backend.tools.file_tool     import FileSystemTool
from backend.tools.shell_tool    import ShellTool
from backend.tools.host_os_tool  import host_os_tool
from backend.tools.code_analyzer_tool import code_analyzer
from backend.tools.data_transform_tool import data_transform_tool
from backend.tools.embedding_tool      import embedding_tool
from backend.tools.git_tool            import git_tool
from backend.tools.http_api_tool       import http_api_tool
from backend.tools.text_editor_tool    import text_editor_tool
from backend.tools.web_search_tool     import web_search_tool
from backend.tools.desktop_tool  import (
    mouse_kb_tool,
    file_tool      as desktop_file_tool,
    document_tool  as desktop_doc_tool,
    browser_tool   as desktop_browser_tool,
)


class ToolRegistry:
    """Registry of available tools for agents."""

    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._initialize_tools()

    # ── Initialisation ─────────────────────────────────────────────────────────

    def _initialize_tools(self):
        """Register all built-in (non-MCP) tools."""
        # ══════════════════════════════════════════════════════════════════════
        # CODE ANALYZER TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="code_analyze",
            description="Analyze code for syntax errors, lint issues, security vulnerabilities, and complexity metrics. Supports Python (pylint, bandit, mypy) and JS/TS.",
            function=code_analyzer.execute,
            parameters={
                "code":           {"type": "string",  "description": "Source code string to analyze", "optional": True},
                "file_path":      {"type": "string",  "description": "Path to code file (alternative to code)", "optional": True},
                "language":       {"type": "string",  "description": "Language: python, javascript, typescript, json, yaml"},
                "analysis_types": {"type": "array",   "description": "Checks to run: syntax, lint, security, complexity, all", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # WEB SEARCH TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="web_search",
            description=(
                "Search the web for current information. "
                "Use when you need up-to-date news, documentation, facts, or any "
                "information that may be beyond your training knowledge. "
                "Returns ranked results with title, URL, and a text snippet for each. "
                "Results are indexed (0, 1, 2 …) for easy citation. "
                "Provider priority (auto): Tavily → Brave → SerpAPI → DuckDuckGo."
            ),
            function=web_search_tool.execute,
            parameters={
                "query":       {"type": "string",  "description": "Natural language search query"},
                "max_results": {"type": "integer", "description": "Number of results to return, 1–10 (default 5)", "optional": True},
                "provider":    {"type": "string",  "description": "Search provider: auto | tavily | brave | serpapi | duckduckgo (default: auto)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # DATA TRANSFORM TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="data_transform",
            description="Convert data between formats (JSON/CSV/XML/YAML/Parquet) and perform transformations: filter, sort, aggregate, deduplicate, flatten.",
            function=data_transform_tool.execute,
            parameters={
                "action":        {"type": "string", "description": "convert, filter, aggregate, sort, deduplicate, flatten"},
                "data":          {"type": "string", "description": "Input data (dict, list, or string)", "optional": True},
                "input_format":  {"type": "string", "description": "Input format: json, csv, yaml, xml", "optional": True},
                "output_format": {"type": "string", "description": "Output format: json, csv, yaml, parquet, excel", "optional": True},
                "file_path":     {"type": "string", "description": "Load data from file path instead of data param", "optional": True},
                "query":         {"type": "string", "description": "Filter query e.g. 'age>18,status=active'", "optional": True},
                "options":       {"type": "object", "description": "Extra options: by, descending, group_by, function, separator", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # EMBEDDING TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="embedding",
            description="Generate vector embeddings for text and compute semantic similarity, search, or clustering. Providers: local (sentence-transformers), openai, cohere.",
            function=embedding_tool.execute,
            parameters={
                "action":     {"type": "string",  "description": "embed, similarity, search, cluster"},
                "texts":      {"type": "string",  "description": "String or list of strings to embed", "optional": True},
                "text_a":     {"type": "string",  "description": "First text for similarity comparison", "optional": True},
                "text_b":     {"type": "string",  "description": "Second text for similarity comparison", "optional": True},
                "query":      {"type": "string",  "description": "Query text for semantic search", "optional": True},
                "candidates": {"type": "array",   "description": "Candidate texts to search through", "optional": True},
                "provider":   {"type": "string",  "description": "Embedding provider: local, openai (default: local)", "optional": True},
                "model":      {"type": "string",  "description": "Model name override (optional)", "optional": True},
                "top_k":      {"type": "integer", "description": "Number of results to return for search (default 5)", "optional": True},
                "n_clusters": {"type": "integer", "description": "Number of clusters for cluster action (default 3)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # GIT TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="git",
            description="Git version control: clone repos, manage branches, view history/diffs, commit and push changes. Not available to task-tier agents (3xxxx).",
            function=git_tool.execute,
            parameters={
                "action":    {"type": "string",  "description": "clone, status, log, diff, checkout, pull, commit, push, branch_list, blame"},
                "repo_url":  {"type": "string",  "description": "Repository URL (for clone)", "optional": True},
                "path":      {"type": "string",  "description": "Local repo path", "optional": True},
                "branch":    {"type": "string",  "description": "Branch name", "optional": True},
                "message":   {"type": "string",  "description": "Commit message", "optional": True},
                "files":     {"type": "array",   "description": "Files to stage for commit (omit to stage all)", "optional": True},
                "commit":    {"type": "string",  "description": "Commit hash for diff", "optional": True},
                "file":      {"type": "string",  "description": "File path for blame", "optional": True},
                "limit":     {"type": "integer", "description": "Number of commits for log (default 10)", "optional": True},
                "remote":    {"type": "string",  "description": "Remote name for push (default: origin)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],  # intentionally excludes 3xxxx
        )

        # ══════════════════════════════════════════════════════════════════════
        # HTTP API TOOL
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="http_api",
            description="Advanced HTTP client: REST calls with auth (Bearer/Basic/API Key), automatic retries with backoff, rate limit tracking, and response parsing (JSON/XML/HTML).",
            function=http_api_tool.execute,
            parameters={
                "url":              {"type": "string",  "description": "Request URL"},
                "method":           {"type": "string",  "description": "HTTP method: GET, POST, PUT, DELETE, PATCH (default: GET)", "optional": True},
                "headers":          {"type": "object",  "description": "Custom request headers", "optional": True},
                "params":           {"type": "object",  "description": "URL query parameters", "optional": True},
                "data":             {"type": "string",  "description": "Raw request body", "optional": True},
                "json_data":        {"type": "object",  "description": "JSON body (sets Content-Type automatically)", "optional": True},
                "auth_type":        {"type": "string",  "description": "Auth method: bearer, basic, api_key", "optional": True},
                "auth_value":       {"type": "string",  "description": "Auth credential (token, user:pass, or key)", "optional": True},
                "timeout":          {"type": "integer", "description": "Request timeout in seconds (default 30)", "optional": True},
                "retries":          {"type": "integer", "description": "Max retry attempts (default 3)", "optional": True},
                "parse_as":         {"type": "string",  "description": "Response parser: json, xml, html, text, auto (default: json)", "optional": True},
                "follow_redirects": {"type": "boolean", "description": "Follow HTTP redirects (default true)", "optional": True},
                "verify_ssl":       {"type": "boolean", "description": "Verify SSL certificates (default true)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )

        self.register_tool(
            name="http_api_batch",
            description="Execute multiple HTTP requests concurrently with controlled concurrency.",
            function=http_api_tool.batch_request,
            parameters={
                "requests":    {"type": "array",   "description": "List of request dicts (same params as http_api)"},
                "concurrency": {"type": "integer", "description": "Max concurrent requests (default 5)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # ORIGINAL BUILT-IN TOOLS
        # ══════════════════════════════════════════════════════════════════════

        # ── Browser Tool (original simple navigate/screenshot) ─────────────────
        browser = BrowserTool()  # single instance shared between both
        self.register_tool(
            name="browser_control",
            description="Control web browser for navigation, form filling, and data extraction",
            function=browser.navigate,
            parameters={
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="browser_screenshot",
            description="Take screenshot of current browser page",
            function=browser.screenshot,
            parameters={
                "path": {"type": "string", "description": "Save path for screenshot"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )

        # ── File Tool (original simple read/write) ─────────────────────────────
        file_tool = FileSystemTool()
        self.register_tool(
            name="read_file",
            description="Read file contents from host filesystem",
            function=file_tool.read_file,
            parameters={
                "filepath": {"type": "string",  "description": "Absolute file path"},
                "limit":    {"type": "integer", "description": "Max characters to read", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="write_file",
            description="Write content to file (Head only)",
            function=file_tool.write_file,
            parameters={
                "filepath": {"type": "string", "description": "Absolute file path"},
                "content":  {"type": "string", "description": "Content to write"},
            },
            authorized_tiers=["0xxxx"],
        )

        # ── Shell Tool ─────────────────────────────────────────────────────────
        shell_tool = ShellTool()
        self.register_tool(
            name="execute_command",
            description="Execute shell command on host system",
            function=shell_tool.execute,
            parameters={
                "command": {"type": "array",   "description": "Command and args as list"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # HOST OS TOOL — cross-platform detection + execution
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="host_detect_os",
            description=(
                "Detect the host system OS outside Docker. Returns full OS profile: "
                "os_family (windows/macos/linux/bsd), distro name, version, "
                "distro_family (debian/rhel/arch/suse/alpine/gentoo/void/nixos/slackware), "
                "architecture, kernel, hostname, package manager, and available operations."
            ),
            function=host_os_tool.detect_os,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="host_list_operations",
            description="List all logical operation names available for cross-platform execution.",
            function=host_os_tool.list_operations,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="host_resolve_command",
            description=(
                "Resolve a logical operation name to the correct OS-native command without executing. "
                "Use to preview what command will run before calling host_execute_for_os."
            ),
            function=host_os_tool.resolve_command,
            parameters={
                "operation":  {"type": "string", "description": "Logical operation name e.g. 'pkg_update'"},
                "os_profile": {"type": "object", "description": "OS profile from host_detect_os (optional)", "optional": True},
                "extra_args": {"type": "array",  "description": "Extra args to append e.g. service name (optional)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="host_execute_for_os",
            description=(
                "Detect host OS and execute the correct command for a logical operation automatically. "
                "Operations: pkg_update, pkg_upgrade, os_version, cpu_info, memory_info, disk_info, "
                "uptime, hostname, network_interfaces, open_ports, ping, dns_lookup, list_processes, "
                "kill_process, list_services, service_start, service_stop, list_users, whoami, "
                "env_vars, installed_packages, kernel_version, architecture."
            ),
            function=host_os_tool.execute_for_os,
            parameters={
                "operation":         {"type": "string",  "description": "Logical operation name"},
                "extra_args":        {"type": "array",   "description": "Extra args e.g. ['nginx'] for service_start", "optional": True},
                "timeout":           {"type": "integer", "description": "Timeout in seconds (default 120)", "optional": True},
                "working_directory": {"type": "string",  "description": "Working directory (optional)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="host_smart_execute",
            description=(
                "Execute a raw command on host with safety checks. "
                "Use host_execute_for_os with a logical operation name when possible."
            ),
            function=host_os_tool.smart_execute,
            parameters={
                "raw_command":       {"type": "array",   "description": "Command and args as list"},
                "timeout":           {"type": "integer", "description": "Timeout in seconds (default 120)", "optional": True},
                "working_directory": {"type": "string",  "description": "Working directory (optional)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # DESKTOP TOOL — mouse, keyboard, files, documents, browser
        # ══════════════════════════════════════════════════════════════════════

        # ── Mouse & Keyboard ───────────────────────────────────────────────────
        self.register_tool(
            name="desktop_mouse_move",
            description="Move mouse cursor to absolute screen coordinates (x, y).",
            function=mouse_kb_tool.move,
            parameters={
                "x":        {"type": "integer", "description": "X coordinate"},
                "y":        {"type": "integer", "description": "Y coordinate"},
                "duration": {"type": "number",  "description": "Movement duration in seconds (default 0.2)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_mouse_click",
            description="Click mouse at coordinates. button: left | right | middle.",
            function=mouse_kb_tool.click,
            parameters={
                "x":      {"type": "integer", "description": "X coordinate"},
                "y":      {"type": "integer", "description": "Y coordinate"},
                "button": {"type": "string",  "description": "left | right | middle (default left)", "optional": True},
                "clicks": {"type": "integer", "description": "Number of clicks (default 1)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_mouse_double_click",
            description="Double-click at screen coordinates.",
            function=mouse_kb_tool.double_click,
            parameters={
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_mouse_right_click",
            description="Right-click at screen coordinates.",
            function=mouse_kb_tool.right_click,
            parameters={
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_mouse_drag",
            description="Click and drag from one position to another.",
            function=mouse_kb_tool.drag,
            parameters={
                "from_x":   {"type": "integer", "description": "Start X"},
                "from_y":   {"type": "integer", "description": "Start Y"},
                "to_x":     {"type": "integer", "description": "End X"},
                "to_y":     {"type": "integer", "description": "End Y"},
                "duration": {"type": "number",  "description": "Drag duration in seconds (default 0.5)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_mouse_scroll",
            description="Scroll at screen position. direction: up | down | left | right.",
            function=mouse_kb_tool.scroll,
            parameters={
                "x":         {"type": "integer", "description": "X coordinate"},
                "y":         {"type": "integer", "description": "Y coordinate"},
                "clicks":    {"type": "integer", "description": "Scroll steps (default 3)", "optional": True},
                "direction": {"type": "string",  "description": "up | down | left | right", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_mouse_position",
            description="Get current mouse cursor (x, y) position.",
            function=mouse_kb_tool.get_position,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_keyboard_type",
            description="Type a string of text at the current cursor position.",
            function=mouse_kb_tool.type_text,
            parameters={
                "text":     {"type": "string", "description": "Text to type"},
                "interval": {"type": "number", "description": "Delay between keystrokes in seconds (default 0.02)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_keyboard_press",
            description=(
                "Press a single key. Supported keys: enter, tab, backspace, delete, escape, "
                "space, up, down, left, right, home, end, pageup, pagedown, f1-f12, "
                "ctrl, alt, shift, win, cmd, and all letter/number keys."
            ),
            function=mouse_kb_tool.press_key,
            parameters={
                "key": {"type": "string", "description": "Key name e.g. 'enter', 'escape', 'f5'"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_keyboard_hotkey",
            description=(
                "Press a key combination simultaneously. "
                "Examples: ['ctrl','c'], ['ctrl','alt','delete'], ['cmd','space']"
            ),
            function=mouse_kb_tool.hotkey,
            parameters={
                "keys": {"type": "array", "description": "List of key names to press together"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_keyboard_key_down",
            description="Hold a key down. Use desktop_keyboard_key_up to release.",
            function=mouse_kb_tool.key_down,
            parameters={
                "key": {"type": "string", "description": "Key name to hold"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_keyboard_key_up",
            description="Release a held key.",
            function=mouse_kb_tool.key_up,
            parameters={
                "key": {"type": "string", "description": "Key name to release"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_screenshot",
            description="Take a screenshot of the entire desktop and save to a file.",
            function=mouse_kb_tool.screenshot,
            parameters={
                "save_path": {"type": "string", "description": "File path to save screenshot (default /tmp/desktop_screenshot.png)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_screen_size",
            description="Get the host screen resolution (width x height).",
            function=mouse_kb_tool.get_screen_size,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_find_on_screen",
            description=(
                "Find a reference image on screen and return its centre coordinates. "
                "Requires opencv-python for confidence-based matching."
            ),
            function=mouse_kb_tool.find_on_screen,
            parameters={
                "image_path": {"type": "string", "description": "Path to reference image (PNG/JPG)"},
                "confidence": {"type": "number", "description": "Match threshold 0.0-1.0 (default 0.9)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )

        # ── File Management ────────────────────────────────────────────────────
        self.register_tool(
            name="desktop_open_file",
            description="Open a file with the OS default application (GUI).",
            function=desktop_file_tool.open_file,
            parameters={
                "filepath": {"type": "string", "description": "Absolute path to file"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_create_file",
            description="Create a new file with optional initial content.",
            function=desktop_file_tool.create_file,
            parameters={
                "filepath": {"type": "string", "description": "Absolute path for new file"},
                "content":  {"type": "string", "description": "Initial file content (optional)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_read_file",
            description="Read file contents with optional line offset and limit.",
            function=desktop_file_tool.read_file,
            parameters={
                "filepath": {"type": "string",  "description": "Absolute path to file"},
                "offset":   {"type": "integer", "description": "Line offset to start reading from (default 0)", "optional": True},
                "limit":    {"type": "integer", "description": "Max lines to return (default 500)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_save_file",
            description="Write content to a file, with optional .bak backup.",
            function=desktop_file_tool.save_file,
            parameters={
                "filepath": {"type": "string",  "description": "Absolute path to file"},
                "content":  {"type": "string",  "description": "Content to write"},
                "backup":   {"type": "boolean", "description": "Create .bak backup before overwriting (default true)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_delete_file",
            description="Delete a file or directory. confirm must be true to proceed.",
            function=desktop_file_tool.delete_file,
            parameters={
                "filepath": {"type": "string",  "description": "Absolute path to file or directory"},
                "confirm":  {"type": "boolean", "description": "Must be true to confirm deletion"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="desktop_copy_file",
            description="Copy a file or directory from src to dst.",
            function=desktop_file_tool.copy_file,
            parameters={
                "src": {"type": "string", "description": "Source path"},
                "dst": {"type": "string", "description": "Destination path"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_move_file",
            description="Move or rename a file or directory.",
            function=desktop_file_tool.move_file,
            parameters={
                "src": {"type": "string", "description": "Source path"},
                "dst": {"type": "string", "description": "Destination path"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_list_directory",
            description="List directory contents with name, size, type, and modified date.",
            function=desktop_file_tool.list_directory,
            parameters={
                "path":        {"type": "string",  "description": "Directory path"},
                "show_hidden": {"type": "boolean", "description": "Include hidden files (default false)", "optional": True},
                "recursive":   {"type": "boolean", "description": "List recursively (default false)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )

        # ── Document Editing ───────────────────────────────────────────────────
        self.register_tool(
            name="desktop_read_document",
            description=(
                "Read a document and return structured content. "
                "Supports: .txt .md .json .csv .docx .xlsx and common code/config files."
            ),
            function=desktop_doc_tool.read_document,
            parameters={
                "filepath": {"type": "string", "description": "Absolute path to document"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_create_document",
            description="Create a new document. doc_type: txt | md | docx | xlsx | json | csv",
            function=desktop_doc_tool.create_document,
            parameters={
                "filepath": {"type": "string", "description": "Path for new document"},
                "content":  {"type": "string", "description": "Initial content (optional, plain text types only)", "optional": True},
                "doc_type": {"type": "string", "description": "txt | md | docx | xlsx | json | csv", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_edit_document",
            description=(
                "Apply structured edits to a document. "
                "For .txt/.md: replace, append, prepend, insert_line, delete_line. "
                "For .docx: append_paragraph, add_heading, add_table, replace. "
                "For .xlsx: set_cell, append_row, add_sheet. "
                "Always creates a .bak backup before editing."
            ),
            function=desktop_doc_tool.edit_document,
            parameters={
                "filepath": {"type": "string", "description": "Absolute path to document"},
                "edits":    {"type": "array",  "description": "List of edit operation dicts"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_save_document",
            description=(
                "Save content to a document. "
                "For .json pass a dict, for .csv pass a list of dicts, for others pass a string."
            ),
            function=desktop_doc_tool.save_document,
            parameters={
                "filepath": {"type": "string",  "description": "Absolute path to document"},
                "content":  {"type": "string",  "description": "Content: string | dict | list"},
                "backup":   {"type": "boolean", "description": "Create .bak backup (default true)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )

        # ── Browser Automation (Playwright, full-featured) ─────────────────────
        self.register_tool(
            name="desktop_browser_navigate",
            description="Navigate to a URL in the automated browser.",
            function=desktop_browser_tool.browse_to,
            parameters={
                "url":        {"type": "string",  "description": "URL to navigate to"},
                "wait_until": {"type": "string",  "description": "domcontentloaded | load | networkidle (default domcontentloaded)", "optional": True},
                "headless":   {"type": "boolean", "description": "Run browser headless (default true)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_get_text",
            description="Extract visible text from a CSS selector on the current page (default: full body).",
            function=desktop_browser_tool.browser_get_text,
            parameters={
                "selector": {"type": "string",  "description": "CSS selector (default 'body')", "optional": True},
                "limit":    {"type": "integer", "description": "Max characters to return (default 5000)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_click",
            description="Click an element on the current page by CSS selector.",
            function=desktop_browser_tool.browser_click,
            parameters={
                "selector": {"type": "string", "description": "CSS selector of element to click"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_type",
            description="Type text into an input field by CSS selector.",
            function=desktop_browser_tool.browser_type,
            parameters={
                "selector":    {"type": "string",  "description": "CSS selector of input field"},
                "text":        {"type": "string",  "description": "Text to type"},
                "clear_first": {"type": "boolean", "description": "Clear field before typing (default true)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_fill_form",
            description=(
                "Fill multiple form fields at once and optionally submit. "
                "fields: {css_selector: value_to_fill}"
            ),
            function=desktop_browser_tool.browser_fill_form,
            parameters={
                "fields":          {"type": "object", "description": "Dict of {css_selector: value}"},
                "submit_selector": {"type": "string", "description": "CSS selector of submit button (optional)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_screenshot",
            description="Take a screenshot of the current browser page.",
            function=desktop_browser_tool.browser_screenshot,
            parameters={
                "save_path": {"type": "string",  "description": "File path to save screenshot", "optional": True},
                "full_page": {"type": "boolean", "description": "Capture full scrollable page (default false)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_scroll",
            description="Scroll the browser page. direction: up | down | top | bottom.",
            function=desktop_browser_tool.browser_scroll,
            parameters={
                "direction": {"type": "string",  "description": "up | down | top | bottom"},
                "amount":    {"type": "integer", "description": "Pixels to scroll (default 500)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_back",
            description="Navigate the browser back to the previous page.",
            function=desktop_browser_tool.browser_back,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_forward",
            description="Navigate the browser forward.",
            function=desktop_browser_tool.browser_forward,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_find_element",
            description="Check if an element exists on the page and return its properties.",
            function=desktop_browser_tool.browser_find_element,
            parameters={
                "selector": {"type": "string", "description": "CSS selector to find"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_execute_js",
            description="Execute JavaScript in the browser page and return the result.",
            function=desktop_browser_tool.browser_execute_js,
            parameters={
                "script": {"type": "string", "description": "JavaScript code to execute"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="desktop_browser_get_links",
            description="Extract all hyperlinks from the current page.",
            function=desktop_browser_tool.browser_get_links,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_download",
            description="Download a file from a URL via the browser.",
            function=desktop_browser_tool.browser_download,
            parameters={
                "url":       {"type": "string", "description": "URL of file to download"},
                "save_path": {"type": "string", "description": "Local path to save the file"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_current_url",
            description="Return the current URL of the open browser page.",
            function=desktop_browser_tool.get_current_url,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="desktop_browser_close",
            description="Close the browser and free all resources.",
            function=desktop_browser_tool.browser_close,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # USER PREFERENCE TOOL
        # ══════════════════════════════════════════════════════════════════════
        from backend.tools.user_preference_tool import user_preference_tool

        self.register_tool(
            name="preference_get",
            description="Get a user preference value. Returns value and editability status.",
            function=user_preference_tool.get_preference,
            parameters={
                "key":        {"type": "string", "description": "Preference key (e.g., 'ui.theme', 'agents.timeout')"},
                "agent_tier": {"type": "string", "description": "Agent tier (0xxxx, 1xxxx, 2xxxx, 3xxxx)"},
                "agent_id":   {"type": "string", "description": "Agentium ID of the calling agent"},
                "user_id":    {"type": "string", "description": "User ID (optional, for user-specific prefs)", "optional": True},
                "default":    {"type": "string", "description": "Default value if preference not found", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )
        self.register_tool(
            name="preference_set",
            description="Set a user preference value. Requires appropriate agent tier permissions.",
            function=user_preference_tool.set_preference,
            parameters={
                "key":        {"type": "string", "description": "Preference key to set"},
                "value":      {"type": "string", "description": "New value (any JSON-serializable type)"},
                "agent_tier": {"type": "string", "description": "Agent tier (0xxxx, 1xxxx, 2xxxx)"},
                "agent_id":   {"type": "string", "description": "Agentium ID of the calling agent"},
                "user_id":    {"type": "string", "description": "User ID (optional)", "optional": True},
                "reason":     {"type": "string", "description": "Reason for the change", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="preference_list",
            description="List all preferences accessible to this agent tier.",
            function=user_preference_tool.list_preferences,
            parameters={
                "agent_tier":     {"type": "string",  "description": "Agent tier (0xxxx, 1xxxx, 2xxxx, 3xxxx)"},
                "agent_id":       {"type": "string",  "description": "Agentium ID of the calling agent"},
                "user_id":        {"type": "string",  "description": "User ID (optional)", "optional": True},
                "category":       {"type": "string",  "description": "Filter by category", "optional": True},
                "include_values": {"type": "boolean", "description": "Include values in response", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )
        self.register_tool(
            name="preference_categories",
            description="Get list of preference categories accessible to this agent tier.",
            function=user_preference_tool.get_categories,
            parameters={
                "agent_tier": {"type": "string", "description": "Agent tier (0xxxx, 1xxxx, 2xxxx, 3xxxx)"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        )
        self.register_tool(
            name="preference_bulk_update",
            description="Update multiple preferences at once. Each update is validated individually.",
            function=user_preference_tool.bulk_update,
            parameters={
                "preferences": {"type": "object", "description": "Map of keys to values {key: value}"},
                "agent_tier":  {"type": "string", "description": "Agent tier (0xxxx, 1xxxx, 2xxxx)"},
                "agent_id":    {"type": "string", "description": "Agentium ID of the calling agent"},
                "user_id":     {"type": "string", "description": "User ID (optional)", "optional": True},
                "reason":      {"type": "string", "description": "Reason for bulk update", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # NODRIVER TOOL — stealth/undetected browser automation
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="nodriver_navigate",
            description=(
                "Navigate the stealth browser to a URL. "
                "Bypasses most WAF / anti-bot protections (Cloudflare, DataDome, etc.). "
                "Returns the page title and resolved URL. "
                "Use new_tab=True to open a parallel session."
            ),
            function=nodriver_tool.navigate,
            parameters={
                "url":        {"type": "string",  "description": "Destination URL (include https://)"},
                "new_tab":    {"type": "boolean", "description": "Open in a new tab (default false)", "optional": True},
                "new_window": {"type": "boolean", "description": "Open in a new window (default false)", "optional": True},
                "timeout":    {"type": "number",  "description": "Page-load timeout in seconds (default 30)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_get_content",
            description="Return the HTML content of the current stealth browser page.",
            function=nodriver_tool.get_content,
            parameters={
                "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_find_element",
            description=(
                "Find a page element by visible text using nodriver's smart shortest-match algorithm. "
                "Retries until timeout. Great for cookie banners, buttons, labels."
            ),
            function=nodriver_tool.find_element,
            parameters={
                "text":       {"type": "string",  "description": "Visible text to search for"},
                "best_match": {"type": "boolean", "description": "Return shortest/closest match (default true)", "optional": True},
                "timeout":    {"type": "number",  "description": "Retry timeout in seconds (default 10)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_find_all_elements",
            description="Find all elements containing the given visible text.",
            function=nodriver_tool.find_all_elements,
            parameters={
                "text":    {"type": "string", "description": "Visible text to search for"},
                "timeout": {"type": "number", "description": "Retry timeout in seconds (default 10)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_select",
            description=(
                "Select a single element by CSS selector (waits until it appears). "
                "Also works inside iframes. "
                "Example selectors: 'input[type=email]', '[role=button]', 'a[href] > div > img'."
            ),
            function=nodriver_tool.select_element,
            parameters={
                "css_selector": {"type": "string", "description": "CSS selector string"},
                "timeout":      {"type": "number", "description": "Retry timeout in seconds (default 10)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_select_all",
            description="Select all elements matching a CSS selector (including inside iframes).",
            function=nodriver_tool.select_all_elements,
            parameters={
                "css_selector": {"type": "string", "description": "CSS selector string"},
                "timeout":      {"type": "number", "description": "Retry timeout in seconds (default 10)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_xpath",
            description="Find a page node using an XPath selector.",
            function=nodriver_tool.xpath,
            parameters={
                "xpath_selector": {"type": "string", "description": "XPath expression"},
                "timeout":        {"type": "number", "description": "Retry timeout in seconds (default 10)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_click",
            description=(
                "Click a page element located by CSS selector OR visible text. "
                "Supply exactly one of 'selector' or 'text'."
            ),
            function=nodriver_tool.click_element,
            parameters={
                "selector":   {"type": "string",  "description": "CSS selector (optional if text given)", "optional": True},
                "text":       {"type": "string",  "description": "Visible text (optional if selector given)", "optional": True},
                "best_match": {"type": "boolean", "description": "Use best-match text algorithm (default true)", "optional": True},
                "timeout":    {"type": "number",  "description": "Retry timeout in seconds (default 10)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_send_keys",
            description="Type text or option values into the element matched by a CSS selector.",
            function=nodriver_tool.send_keys,
            parameters={
                "selector": {"type": "string", "description": "CSS selector for the target element"},
                "keys":     {"type": "string", "description": "Text / keys to send"},
                "timeout":  {"type": "number", "description": "Retry timeout in seconds (default 10)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_evaluate",
            description=(
                "Execute arbitrary JavaScript in the current page context and return the result. "
                "Example: {\"expression\": \"document.querySelectorAll('a').length\"}"
            ),
            function=nodriver_tool.evaluate,
            parameters={
                "expression": {"type": "string", "description": "JavaScript expression to evaluate"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_scroll",
            description="Scroll the current page up or down by a pixel amount.",
            function=nodriver_tool.scroll,
            parameters={
                "amount":    {"type": "integer", "description": "Pixels to scroll (default 200)", "optional": True},
                "direction": {"type": "string",  "description": "'down' or 'up' (default 'down')", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_screenshot",
            description="Save a screenshot of the current stealth browser page to a file.",
            function=nodriver_tool.screenshot,
            parameters={
                "save_path": {"type": "string", "description": "File path to save PNG (default /tmp/nodriver_screenshot.png)", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_save_cookies",
            description="Save current session cookies to a JSON file for reuse across runs.",
            function=nodriver_tool.save_cookies,
            parameters={
                "filepath": {"type": "string", "description": "Destination file path for cookies JSON"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_load_cookies",
            description="Restore session cookies from a JSON file (previously saved by nodriver_save_cookies).",
            function=nodriver_tool.load_cookies,
            parameters={
                "filepath": {"type": "string", "description": "Source file path for cookies JSON"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_get_local_storage",
            description="Read the current page's localStorage and return it as a dict.",
            function=nodriver_tool.get_local_storage,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_set_local_storage",
            description="Write key-value pairs into the current page's localStorage.",
            function=nodriver_tool.set_local_storage,
            parameters={
                "data": {"type": "object", "description": "Dict of key-value pairs to set"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_cf_verify",
            description=(
                "Automatically click the Cloudflare 'I am human' checkbox. "
                "Requires opencv-python. Only works in non-expert mode."
            ),
            function=nodriver_tool.cf_verify,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_bypass_insecure_warning",
            description="Click through the browser's 'your connection is not private' warning (e.g. for self-signed certs).",
            function=nodriver_tool.bypass_insecure_warning,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_reload",
            description="Reload the current stealth browser page.",
            function=nodriver_tool.reload,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_close_tab",
            description="Close the currently active stealth browser tab.",
            function=nodriver_tool.close_tab,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="nodriver_close",
            description="Shut down the stealth browser entirely and free all resources.",
            function=nodriver_tool.close,
            parameters={},
            authorized_tiers=["0xxxx", "1xxxx"],
        )

        # ══════════════════════════════════════════════════════════════════════
        # TEXT EDITOR TOOL — view, create, str_replace, insert, undo
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="text_editor",
            description=(
                "Persistent text-file editor with undo history. "
                "Actions: view (read file or line range), create (write new file), "
                "str_replace (replace a unique string — fails if 0 or >1 occurrences), "
                "insert (insert text before a 1-based line number), "
                "undo_edit (revert the last change to a file)."
            ),
            function=text_editor_tool.execute,
            parameters={
                "action":      {"type": "string",  "description": "view | create | str_replace | insert | undo_edit"},
                "path":        {"type": "string",  "description": "Absolute path to the target file"},
                "content":     {"type": "string",  "description": "Full file content — required for 'create'", "optional": True},
                "old_str":     {"type": "string",  "description": "Exact unique string to find — required for 'str_replace'", "optional": True},
                "new_str":     {"type": "string",  "description": "Replacement text — required for 'str_replace' (use '' to delete)", "optional": True},
                "insert_line": {"type": "integer", "description": "1-based line number to insert before — required for 'insert'", "optional": True},
                "insert_text": {"type": "string",  "description": "Text to insert — required for 'insert'", "optional": True},
                "view_range":  {"type": "array",   "description": "[start_line, end_line] for partial view — optional for 'view'", "optional": True},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx"],
        )

    # ── Registration ───────────────────────────────────────────────────────────

    def register_tool(
        self,
        name: str,
        description: str,
        function: Callable,
        parameters: Dict[str, Any],
        authorized_tiers: Optional[List[str]] = None,
    ) -> None:
        self.tools[name] = {
            "name":             name,
            "description":      description,
            "function":         function,
            "parameters":       parameters,
            "authorized_tiers": authorized_tiers or [],
        }

    # ── Queries ────────────────────────────────────────────────────────────────

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        return self.tools.get(name)

    def list_tools(self, agent_tier: str) -> Dict[str, Any]:
        available: Dict[str, Any] = {}
        for name, tool in self.tools.items():
            if agent_tier not in tool["authorized_tiers"]:
                continue
            descriptor: Dict[str, Any] = {
                "description": tool["description"],
                "parameters":  tool["parameters"],
            }
            if tool.get("deprecated"):
                descriptor["deprecated"]         = True
                descriptor["deprecation_reason"] = tool.get("deprecation_reason")
                descriptor["replacement"]        = tool.get("replacement")
            if tool.get("is_mcp"):
                descriptor["is_mcp"]            = True
                descriptor["mcp_tier"]          = tool.get("mcp_tier")
                descriptor["mcp_server_url"]    = tool.get("mcp_server_url")
                descriptor["mcp_original_name"] = tool.get("mcp_original_name")
            available[name] = descriptor
        return available

    # ── Execution ──────────────────────────────────────────────────────────────

    def execute_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        tool = self.get_tool(name)
        if not tool:
            return {"status": "error", "error": f"Tool '{name}' not found"}
        try:
            fn = tool["function"]
            if inspect.iscoroutinefunction(fn):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, fn(**kwargs))
                        result = future.result(timeout=60)
                else:
                    result = asyncio.run(fn(**kwargs))
            else:
                result = fn(**kwargs)
            return result
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def execute_tool_async(self, name: str, **kwargs) -> Dict[str, Any]:
        tool = self.get_tool(name)
        if not tool:
            return {"status": "error", "error": f"Tool '{name}' not found"}
        try:
            fn = tool["function"]
            if inspect.iscoroutinefunction(fn):
                result = await fn(**kwargs)
            else:
                loop   = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: fn(**kwargs))
            return result
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ── Lifecycle helpers ──────────────────────────────────────────────────────

    def get_tool_function(self, name: str) -> Optional[Callable]:
        tool = self.tools.get(name)
        return tool["function"] if tool else None

    def update_tool_function(self, name: str, function: Callable) -> bool:
        if name not in self.tools:
            return False
        self.tools[name]["function"] = function
        return True

    def mark_deprecated(self, name: str, reason: str,
                        replacement: Optional[str] = None) -> bool:
        if name not in self.tools:
            return False
        self.tools[name]["deprecated"]         = True
        self.tools[name]["deprecation_reason"] = reason
        self.tools[name]["replacement"]        = replacement
        return True

    def unmark_deprecated(self, name: str) -> bool:
        if name not in self.tools:
            return False
        self.tools[name].pop("deprecated", None)
        self.tools[name].pop("deprecation_reason", None)
        self.tools[name].pop("replacement", None)
        return True

    def deregister_tool(self, name: str) -> bool:
        if name not in self.tools:
            return False
        del self.tools[name]
        return True

    # ── API Schema Export ──────────────────────────────────────────────────────

    def _build_props(self, tool: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert internal parameter dict → JSON Schema properties + required list.

        Internal type names are normalised to valid JSON Schema types.
        Parameters tagged "optional": True are excluded from the required list.
        """
        TYPE_MAP: Dict[str, str] = {
            "string":  "string",
            "integer": "integer",
            "number":  "number",
            "boolean": "boolean",
            "array":   "array",
            "object":  "object",
            "any":     "string",   # broad fallback — agents stringify complex values
        }

        props: Dict[str, Any] = {}
        required: List[str] = []

        for param_name, meta in tool.get("parameters", {}).items():
            raw_type = meta.get("type", "string")
            json_type = TYPE_MAP.get(raw_type, "string")

            prop: Dict[str, Any] = {
                "type":        json_type,
                "description": meta.get("description", ""),
            }
            if "enum" in meta:
                prop["enum"] = meta["enum"]

            props[param_name] = prop

            if not meta.get("optional", False):
                required.append(param_name)

        return props, required

    def to_openai_tools(self, tier: str) -> List[Dict[str, Any]]:
        """
        Export tier-filtered tools in OpenAI function-calling format.

        Compatible with OpenAI, Groq, Mistral, Together, Fireworks, DeepSeek,
        Moonshot, Azure, Gemini (OpenAI-compat), Ollama, llama.cpp, LM Studio.
        Deprecated tools are excluded.
        """
        result: List[Dict[str, Any]] = []
        for name, tool in self.tools.items():
            if tier not in tool.get("authorized_tiers", []):
                continue
            if tool.get("deprecated"):
                continue
            props, required = self._build_props(tool)
            result.append({
                "type": "function",
                "function": {
                    "name":        name,
                    "description": tool.get("description", ""),
                    "parameters": {
                        "type":       "object",
                        "properties": props,
                        "required":   required,
                    },
                },
            })
        return result

    def to_anthropic_tools(self, tier: str) -> List[Dict[str, Any]]:
        """
        Export tier-filtered tools in Anthropic input_schema format.

        Used exclusively by AnthropicProvider.generate_with_tools().
        Deprecated tools are excluded.
        """
        result: List[Dict[str, Any]] = []
        for name, tool in self.tools.items():
            if tier not in tool.get("authorized_tiers", []):
                continue
            if tool.get("deprecated"):
                continue
            props, required = self._build_props(tool)
            result.append({
                "name":        name,
                "description": tool.get("description", ""),
                "input_schema": {
                    "type":       "object",
                    "properties": props,
                    "required":   required,
                },
            })
        return result


# Global registry instance
tool_registry = ToolRegistry()