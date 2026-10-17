"""
Prompt Injection Sanitizer
==========================
Detects and removes prompt injection attempts from text before it reaches LLMs.

Injection patterns covered:
- Role manipulation: "Ignore previous instructions", "You are now...", "Act as..."
- Instruction override: "SYSTEM:", "ASSISTANT:", "Override:", "New instructions:"
- Context breaking: "```", "---END---", "<<INJECTION>>", special delimiters
- Tool/command injection: "execute(", "eval(", "subprocess", "os.system"
- Data exfiltration: "Print your prompt", "Show system prompt", "Repeat instructions"
- Chain of Thought manipulation: "Think step by step but ignore...", "Reasoning: ..."
"""

import re
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class InjectionType(str, Enum):
    """Categories of prompt injection patterns."""
    ROLE_MANIPULATION = "role_manipulation"
    INSTRUCTION_OVERRIDE = "instruction_override"
    CONTEXT_BREAKING = "context_breaking"
    TOOL_COMMAND_INJECTION = "tool_command_injection"
    DATA_EXFILTRATION = "data_exfiltration"
    COT_MANIPULATION = "cot_manipulation"
    ENCODING_OBFUSCATION = "encoding_obfuscation"


@dataclass
class DetectionResult:
    """Result of prompt injection detection."""
    detected: bool
    injection_types: List[InjectionType] = field(default_factory=list)
    matched_patterns: List[str] = field(default_factory=list)
    sanitized_text: str = ""
    confidence: float = 0.0  # 0.0 - 1.0


class PromptInjectionSanitizer:
    """
    Sanitizes text to remove prompt injection attempts.

    Usage:
        sanitizer = PromptInjectionSanitizer()
        result = sanitizer.sanitize(user_input)
        if result.detected:
            logger.warning(f"Prompt injection detected: {result.injection_types}")
        clean_text = result.sanitized_text
    """

    # ─── Role Manipulation Patterns ───
    ROLE_PATTERNS = [
        r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|above)?\s*instructions?",
        r"(?i)forget\s+(?:all\s+)?(?:previous|prior|above)?\s*instructions?",
        r"(?i)forget\s+(?:everything|all)\s+(?:you\s+)?(?:were\s+)?told",
        r"(?i)you\s+are\s+(?:now\s+)?(?:a|an)\s+\w+",
        r"(?i)act\s+as\s+(?:a|an)?\s*\w+",
        r"(?i)pretend\s+(?:to\s+be|you\s+are)\s+(?:a|an)\s+\w+",
        r"(?i)roleplay\s+(?:as|:)",
        r"(?i)simulate\s+(?:a|an)\s+\w+",
        r"(?i)become\s+(?:a|an)\s+\w+",
        r"(?i)adopt\s+(?:the\s+)?(?:persona|role|identity)\s+of",
        r"(?i)from\s+now\s+on\s+you\s+are",
        r"(?i)your\s+new\s+(?:role|identity|persona)\s+is",
    ]

    # ─── Instruction Override Patterns ───
    INSTRUCTION_PATTERNS = [
        r"(?i)^\s*system\s*:",
        r"(?i)^\s*assistant\s*:",
        r"(?i)^\s*user\s*:",
        r"(?i)^\s*human\s*:",
        r"(?i)^\s*ai\s*:",
        r"(?i)override\s+(?:previous\s+)?instructions?",
        r"(?i)new\s+instructions?\s*:",
        r"(?i)updated\s+instructions?\s*:",
        r"(?i)disregard\s+(?:all\s+)?(?:previous\s+)?instructions?",
        r"(?i)replace\s+(?:all\s+)?(?:previous\s+)?instructions?",
        r"(?i)supersede\s+(?:all\s+)?(?:previous\s+)?instructions?",
        r"(?i)system\s+prompt\s*[:=]",
        r"(?i)prompt\s*[:=]",
        r"(?i)instruction\s*[:=]",
    ]

    # ─── Context Breaking Patterns ───
    CONTEXT_BREAKING_PATTERNS = [
        r"```\s*(?:python|javascript|bash|sh|sql|json|xml|html|markdown|text)?\s*\n",
        r"```",
        r"---+\s*END\s*---+",
        r"<<\s*(?:INJECTION|OVERRIDE|SYSTEM|PROMPT)\s*>>",
        r"\[\s*(?:INJECTION|OVERRIDE|SYSTEM|PROMPT)\s*\]",
        r"\{\s*(?:INJECTION|OVERRIDE|SYSTEM|PROMPT)\s*\}",
        r"<\|\s*(?:endoftext|im_start|im_end)\s*\|>",
        r"<\|.*?\|>",
        r"\[INST\]|\[/INST\]",
        r"<<SYS>>|<</SYS>>",
        r"###\s*(?:SYSTEM|USER|ASSISTANT)\s*###",
    ]

    # ─── Tool/Command Injection Patterns ───
    TOOL_COMMAND_PATTERNS = [
        r"(?i)\bexecute\s*\(",
        r"(?i)\beval\s*\(",
        r"(?i)\bexec\s*\(",
        r"(?i)__import__\s*\(",
        r"(?i)importlib\.",
        r"(?i)subprocess\.(?:call|run|Popen|check_output)",
        r"(?i)os\.system\s*\(",
        r"(?i)os\.popen\s*\(",
        r"(?i)compile\s*\(",
        r"(?i)getattr\s*\(",
        r"(?i)setattr\s*\(",
        r"(?i)delattr\s*\(",
        r"(?i)globals\s*\(\s*\)",
        r"(?i)locals\s*\(\s*\)",
        r"(?i)vars\s*\(\s*\)",
        r"(?i)breakpoint\s*\(",
        r"(?i)\[.*?\]\(\s*javascript\s*:.*?\)",
    ]

    # ─── Data Exfiltration Patterns ───
    EXFILTRATION_PATTERNS = [
        r"(?i)print\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)show\s+(?:me\s+)?(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)repeat\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)output\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)display\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)reveal\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)what\s+(?:is|are)\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)tell\s+me\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)give\s+me\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)dump\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)leak\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)expose\s+(?:your|the|my)?\s*(?:system\s+)?prompt",
        r"(?i)tell\s+me\s+(?:your|the|my)?\s*(?:instructions|rules)",
        r"(?i)what\s+(?:are|were)\s+(?:your|the|my)?\s*(?:instructions|rules)",
        r"(?i)show\s+me\s+(?:your|the|my)?\s*(?:instructions|rules)",
        r"(?i)previous\s+(?:instructions|prompts|messages)",
        r"(?i)conversation\s+history",
        r"(?i)context\s+window",
    ]

    # ─── Chain of Thought Manipulation Patterns ───
    COT_PATTERNS = [
        r"(?i)think\s+step\s+by\s+step\s+but\s+ignore",
        r"(?i)reasoning\s*:\s*ignore",
        r"(?i)chain\s+of\s+thought\s*:\s*ignore",
        r"(?i)internal\s+monologue\s*:\s*ignore",
        r"(?i)scratchpad\s*:\s*ignore",
        r"(?i)don't\s+output\s+(?:your\s+)?(?:reasoning|thoughts|analysis)",
        r"(?i)hide\s+(?:your\s+)?(?:reasoning|thoughts|analysis)",
        r"(?i)suppress\s+(?:your\s+)?(?:reasoning|thoughts|analysis)",
    ]

    # ─── Encoding Obfuscation Patterns ───
    ENCODING_PATTERNS = [
        r"(?i)base64\s*[:=]",
        r"(?i)rot13\s*[:=]",
        r"(?i)encoded\s*[:=]",
        r"(?i)decode\s+(?:this|the\s+following)",
        r"\\x[0-9a-fA-F]{2}",
        r"\\u[0-9a-fA-F]{4}",
        r"%[0-9a-fA-F]{2}",
    ]

    # Combined patterns with types
    ALL_PATTERNS: List[tuple[InjectionType, List[str]]] = [
        (InjectionType.ROLE_MANIPULATION, ROLE_PATTERNS),
        (InjectionType.INSTRUCTION_OVERRIDE, INSTRUCTION_PATTERNS),
        (InjectionType.CONTEXT_BREAKING, CONTEXT_BREAKING_PATTERNS),
        (InjectionType.TOOL_COMMAND_INJECTION, TOOL_COMMAND_PATTERNS),
        (InjectionType.DATA_EXFILTRATION, EXFILTRATION_PATTERNS),
        (InjectionType.COT_MANIPULATION, COT_PATTERNS),
        (InjectionType.ENCODING_OBFUSCATION, ENCODING_PATTERNS),
    ]

    def __init__(
        self,
        *,
        strip_matches: bool = True,
        replacement: str = "[REDACTED: prompt injection]",
        log_detections: bool = True,
    ):
        """
        Initialize the sanitizer.

        Args:
            strip_matches: If True, remove matched patterns. If False, only detect.
            replacement: String to replace matched patterns with.
            log_detections: Whether to log detected injections.
        """
        self.strip_matches = strip_matches
        self.replacement = replacement
        self.log_detections = log_detections
        self._compiled_patterns: List[tuple[InjectionType, List[re.Pattern]]] = []
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile all regex patterns for performance."""
        for inj_type, patterns in self.ALL_PATTERNS:
            compiled = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns]
            self._compiled_patterns.append((inj_type, compiled))

    def detect(self, text: str) -> DetectionResult:
        """
        Detect prompt injection patterns without modifying the text.

        Args:
            text: Input text to scan.

        Returns:
            DetectionResult with detection details.
        """
        if not text:
            return DetectionResult(detected=False, sanitized_text="")

        detected_types: List[InjectionType] = []
        matched_patterns: List[str] = []

        # Check for zero-width / bidi obfuscation characters
        normalized_text = re.sub(r"[\u200B-\u200D\uFEFF\u202E\u202D]", "", text)
        if len(normalized_text) != len(text):
            detected_types.append(InjectionType.ENCODING_OBFUSCATION)
            matched_patterns.append("zero_width_or_bidi_character")

        for inj_type, compiled_patterns in self._compiled_patterns:
            for pattern in compiled_patterns:
                matches = pattern.findall(text)
                if matches:
                    detected_types.append(inj_type)
                    matched_patterns.extend([str(m) for m in matches])
                elif normalized_text != text:
                    norm_matches = pattern.findall(normalized_text)
                    if norm_matches:
                        detected_types.append(inj_type)
                        detected_types.append(InjectionType.ENCODING_OBFUSCATION)
                        matched_patterns.extend([str(m) for m in norm_matches])

        # Deduplicate while preserving order
        unique_types = list(dict.fromkeys(detected_types))
        unique_matches = list(dict.fromkeys(matched_patterns))

        # Calculate confidence based on number and severity of detections
        confidence = min(1.0, len(unique_matches) * 0.15 + len(unique_types) * 0.1)

        if self.log_detections and unique_types:
            logger.warning(
                f"Prompt injection detected: types={[t.value for t in unique_types]}, "
                f"matches={len(unique_matches)}, confidence={confidence:.2f}"
            )

        return DetectionResult(
            detected=len(unique_types) > 0,
            injection_types=unique_types,
            matched_patterns=unique_matches,
            sanitized_text=text,  # Unmodified in detect-only mode
            confidence=confidence,
        )

    def sanitize(self, text: str) -> DetectionResult:
        """
        Detect and sanitize prompt injection patterns from text.

        Args:
            text: Input text to sanitize.

        Returns:
            DetectionResult with sanitized text and detection details.
        """
        if not text:
            return DetectionResult(detected=False, sanitized_text="")

        result = self.detect(text)

        if not result.detected or not self.strip_matches:
            return DetectionResult(
                detected=result.detected,
                injection_types=result.injection_types,
                matched_patterns=result.matched_patterns,
                sanitized_text=text,
                confidence=result.confidence,
            )

        # Apply sanitization by stripping obfuscation characters and replacing matched patterns
        sanitized = re.sub(r"[\u200B-\u200D\uFEFF\u202E\u202D]", "", text)
        for inj_type, compiled_patterns in self._compiled_patterns:
            for pattern in compiled_patterns:
                sanitized = pattern.sub(self.replacement, sanitized)

        return DetectionResult(
            detected=result.detected,
            injection_types=result.injection_types,
            matched_patterns=result.matched_patterns,
            sanitized_text=sanitized,
            confidence=result.confidence,
        )

    def sanitize_dict(self, data: Dict[str, Any], keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Sanitize string values in a dictionary.

        Args:
            data: Dictionary to sanitize.
            keys: Specific keys to sanitize. If None, sanitize all string values.

        Returns:
            Dictionary with sanitized string values.
        """
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            if keys is not None and key not in keys:
                result[key] = value
                continue

            if isinstance(value, str):
                sanitized_result = self.sanitize(value)
                result[key] = sanitized_result.sanitized_text
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value, keys)
            elif isinstance(value, list):
                result[key] = [
                    self.sanitize_dict(item, keys) if isinstance(item, dict)
                    else self.sanitize(item).sanitized_text if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value

        return result


# Global instance for convenience
prompt_injection_sanitizer = PromptInjectionSanitizer()


def sanitize_prompt_injection(text: str, *, strip: bool = True) -> str:
    """
    Convenience function to sanitize text for prompt injection.

    Args:
        text: Text to sanitize.
        strip: Whether to strip detected patterns.

    Returns:
        Sanitized text.
    """
    sanitizer = PromptInjectionSanitizer(strip_matches=strip)
    return sanitizer.sanitize(text).sanitized_text


def detect_prompt_injection(text: str) -> DetectionResult:
    """
    Convenience function to detect prompt injection without sanitizing.

    Args:
        text: Text to scan.

    Returns:
        DetectionResult with detection details.
    """
    return prompt_injection_sanitizer.detect(text)