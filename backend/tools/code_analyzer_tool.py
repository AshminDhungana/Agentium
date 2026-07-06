"""
Code Analysis Tool — Static analysis, linting, and code quality checks.

Provides:
- Syntax validation for Python, JavaScript, TypeScript, etc.
- Static analysis (pylint, eslint, mypy)
- Code complexity metrics (cyclomatic complexity)
- Security vulnerability scanning (bandit, semgrep)
- Dependency analysis
"""

import ast
import subprocess
import tempfile
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import pylint.lint
    from pylint.reporters.json_reporter import JSONReporter
    PYLINT_AVAILABLE = True
except ImportError:
    PYLINT_AVAILABLE = False

try:
    from bandit.core import manager as bandit_manager
    BANDIT_AVAILABLE = True
except ImportError:
    BANDIT_AVAILABLE = False


class CodeAnalyzerTool:
    """
    Analyze code quality, security, and structure.
    """
    
    TOOL_NAME = "code_analyzer"
    TOOL_DESCRIPTION = """
    Analyze code for quality, security, and structural issues.
    
    Supports:
    - Python: pylint, mypy, bandit (security), ast parsing
    - JavaScript/TypeScript: eslint (if available)
    - General: syntax validation, complexity metrics
    
    Use for:
    - Validating agent-generated code before execution
    - Security scanning of external code
    - Code review automation
    - Complexity analysis for refactoring decisions
    """
    
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx", "3xxxx"]
    
    SUPPORTED_LANGUAGES = {
        "python": [".py"],
        "javascript": [".js", ".jsx"],
        "typescript": [".ts", ".tsx"],
        "json": [".json"],
        "yaml": [".yaml", ".yml"],
        "markdown": [".md"],
    }
    
    def __init__(self):
        self._temp_dir = Path("/tmp/code_analysis")
        self._temp_dir.mkdir(parents=True, exist_ok=True)
    
    async def execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        language: str = "python",
        analysis_types: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute code analysis.
        
        Args:
            code: Source code string (alternative to file_path)
            file_path: Path to code file
            language: Programming language
            analysis_types: List of checks - syntax, lint, security, complexity, all
        """
        if not analysis_types:
            analysis_types = ["all"]
        
        # Get code content
        if file_path:
            source = Path(file_path).read_text()
        elif code:
            source = code
        else:
            return {"success": False, "error": "Provide code or file_path"}
        
        results = {
            "success": True,
            "language": language,
            "lines_of_code": len(source.splitlines()),
            "analysis": {}
        }
        
        # Run requested analyses
        if "all" in analysis_types or "syntax" in analysis_types:
            results["analysis"]["syntax"] = self._check_syntax(source, language)
        
        if "all" in analysis_types or "complexity" in analysis_types:
            results["analysis"]["complexity"] = self._analyze_complexity(source, language)
        
        if language == "python":
            if ("all" in analysis_types or "lint" in analysis_types) and PYLINT_AVAILABLE:
                results["analysis"]["lint"] = self._pylint_check(source)
            
            if ("all" in analysis_types or "security" in analysis_types) and BANDIT_AVAILABLE:
                results["analysis"]["security"] = self._bandit_check(source)
            
            results["analysis"]["imports"] = self._extract_imports(source)
            results["analysis"]["functions"] = self._extract_functions(source)
        
        # Calculate overall score
        results["quality_score"] = self._calculate_score(results["analysis"])
        
        return results
    
    def _check_syntax(self, source: str, language: str) -> Dict[str, Any]:
        """Validate syntax."""
        try:
            if language == "python":
                ast.parse(source)
                return {"valid": True, "errors": []}
            elif language in ["javascript", "typescript", "json"]:
                # Use node for JS/TS/JSON validation if available
                result = subprocess.run(
                    ["node", "--check", "-"],
                    input=source if language == "javascript" else f"JSON.parse({json.dumps(source)})",
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return {
                    "valid": result.returncode == 0,
                    "errors": [result.stderr] if result.returncode != 0 else []
                }
            else:
                return {"valid": True, "errors": [], "note": "Syntax check not implemented for this language"}
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [{
                    "line": e.lineno,
                    "column": e.offset,
                    "message": str(e)
                }]
            }
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}
    
    def _analyze_complexity(self, source: str, language: str) -> Dict[str, Any]:
        """Calculate cyclomatic complexity and other metrics."""
        if language != "python":
            return {"note": "Complexity analysis only available for Python"}
        
        try:
            tree = ast.parse(source)
            
            # Count various structures
            functions = len([n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))])
            classes = len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])
            if_statements = len([n for n in ast.walk(tree) if isinstance(n, ast.If)])
            for_loops = len([n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.AsyncFor))])
            while_loops = len([n for n in ast.walk(tree) if isinstance(n, ast.While)])
            try_blocks = len([n for n in ast.walk(tree) if isinstance(n, ast.Try)])
            
            # Simple complexity estimation
            complexity = 1 + if_statements + for_loops + while_loops + try_blocks
            
            return {
                "cyclomatic_complexity": complexity,
                "functions": functions,
                "classes": classes,
                "branches": if_statements,
                "loops": for_loops + while_loops,
                "try_blocks": try_blocks,
                "rating": "low" if complexity < 10 else "medium" if complexity < 20 else "high"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _pylint_check(self, source: str) -> Dict[str, Any]:
        """Run pylint analysis."""
        if not PYLINT_AVAILABLE:
            return {"error": "pylint not installed"}
        
        try:
            # Write to temp file
            temp_file = self._temp_dir / f"analyze_{id(source)}.py"
            temp_file.write_text(source)
            
            # Run pylint
            from io import StringIO
            pylint_output = StringIO()
            reporter = JSONReporter(pylint_output)
            
            pylint.lint.Run(
                [str(temp_file), "--output-format=json"],
                reporter=reporter,
                exit=False
            )
            
            # Parse results
            output = pylint_output.getvalue()
            if output:
                issues = json.loads(output)
            else:
                issues = []
            
            # Categorize
            errors = [i for i in issues if i.get("type") == "error"]
            warnings = [i for i in issues if i.get("type") == "warning"]
            conventions = [i for i in issues if i.get("type") == "convention"]
            
            # Cleanup
            temp_file.unlink(missing_ok=True)
            
            return {
                "score": max(0, 10 - len(errors) * 2 - len(warnings) * 0.5),
                "errors": errors[:10],  # Limit
                "warnings": warnings[:10],
                "conventions": len(conventions),
                "total_issues": len(issues)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _bandit_check(self, source: str) -> Dict[str, Any]:
        """Run bandit security scan."""
        if not BANDIT_AVAILABLE:
            return {"error": "bandit not installed"}
        
        try:
            temp_file = self._temp_dir / f"bandit_{id(source)}.py"
            temp_file.write_text(source)
            
            # Run bandit
            from bandit.core import config as bandit_config
            conf = bandit_config.BanditConfig()
            mgr = bandit_manager.BanditManager(conf, "file", str(temp_file))
            mgr.run_tests()
            
            issues = []
            for issue in mgr.get_issue_list():
                issues.append({
                    "severity": issue.severity,
                    "confidence": issue.confidence,
                    "text": issue.text,
                    "line": issue.lineno
                })
            
            temp_file.unlink(missing_ok=True)
            
            high = [i for i in issues if i["severity"] == "HIGH"]
            medium = [i for i in issues if i["severity"] == "MEDIUM"]
            low = [i for i in issues if i["severity"] == "LOW"]
            
            return {
                "safe": len(issues) == 0,
                "high_severity": high,
                "medium_severity": medium[:5],
                "low_severity": len(low),
                "recommendation": "Review high severity issues before execution" if high else "No critical security issues found"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _extract_imports(self, source: str) -> List[str]:
        """Extract imported modules."""
        try:
            tree = ast.parse(source)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom):
                    imports.append(f"{node.module}.{node.names[0].name}" if node.names else node.module)
            return list(set(imports))
        except:
            return []
    
    def _extract_functions(self, source: str) -> List[Dict[str, Any]]:
        """Extract function definitions."""
        try:
            tree = ast.parse(source)
            functions = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": len(node.args.args),
                        "async": isinstance(node, ast.AsyncFunctionDef)
                    })
            return functions
        except:
            return []
    
    def _calculate_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate overall quality score (0-100)."""
        scores = []
        
        if "syntax" in analysis:
            scores.append(100 if analysis["syntax"].get("valid") else 0)
        
        if "lint" in analysis and "score" in analysis["lint"]:
            scores.append(analysis["lint"]["score"] * 10)
        
        if "security" in analysis:
            sec = analysis["security"]
            if "safe" in sec:
                scores.append(100 if sec["safe"] else 50)
        
        if "complexity" in analysis:
            comp = analysis["complexity"]
            if "cyclomatic_complexity" in comp:
                c = comp["cyclomatic_complexity"]
                scores.append(100 if c < 10 else 70 if c < 20 else 40)
        
        return sum(scores) / len(scores) if scores else 0


# Global instance
code_analyzer = CodeAnalyzerTool()