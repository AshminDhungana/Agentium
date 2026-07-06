"""
Data Transform Tool — Convert between formats and transform data.

Provides:
- Format conversion: JSON ↔ CSV ↔ XML ↔ YAML ↔ Parquet
- Data cleaning: deduplication, normalization
- Filtering and aggregation
- Schema validation
"""

import json
import csv
import xml.etree.ElementTree as ET
from io import StringIO
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import pyarrow
    import pyarrow.parquet
    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False


class DataTransformTool:
    """
    Transform and convert data between formats.
    """
    
    TOOL_NAME = "data_transform"
    TOOL_DESCRIPTION = """
    Transform data between formats and perform cleaning operations.
    
    Conversions:
    - JSON ↔ CSV ↔ XML ↔ YAML ↔ Parquet ↔ Excel
    
    Transformations:
    - Filter rows by conditions
    - Sort by columns
    - Aggregate (group by, sum, count, avg)
    - Deduplicate
    - Normalize/flatten nested structures
    
    Use for:
    - Preparing data for analysis
    - Converting API responses to usable formats
    - Cleaning datasets before storage
    """
    
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx", "3xxxx"]
    
    async def execute(
        self,
        action: str,
        data: Optional[Any] = None,
        input_format: str = "json",
        output_format: str = "csv",
        file_path: Optional[str] = None,
        query: Optional[str] = None,
        options: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute data transformation."""
        
        # Load data
        if file_path:
            data = self._load_from_file(file_path, input_format)
        elif isinstance(data, str):
            data = self._parse_string(data, input_format)
        
        if data is None:
            return {"success": False, "error": "No data provided"}
        
        # Execute action
        if action == "convert":
            result = self._convert(data, output_format, options or {})
        elif action == "filter":
            result = self._filter_data(data, query, options or {})
        elif action == "aggregate":
            result = self._aggregate(data, options or {})
        elif action == "sort":
            result = self._sort(data, options or {})
        elif action == "deduplicate":
            result = self._deduplicate(data, options or {})
        elif action == "flatten":
            result = self._flatten(data, options or {})
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
        
        return {
            "success": True,
            "action": action,
            "input_format": input_format,
            "output_format": output_format,
            "result": result,
            "record_count": len(result) if isinstance(result, list) else 1
        }
    
    def _load_from_file(self, path: str, format: str) -> Any:
        """Load data from file."""
        p = Path(path)
        if not p.exists():
            raise ValueError(f"File not found: {path}")
        
        content = p.read_text()
        return self._parse_string(content, format)
    
    def _parse_string(self, content: str, format: str) -> Any:
        """Parse string content."""
        if format == "json":
            return json.loads(content)
        elif format == "csv":
            return list(csv.DictReader(StringIO(content)))
        elif format == "yaml" and YAML_AVAILABLE:
            return yaml.safe_load(content)
        elif format == "xml":
            # Simple XML to dict conversion
            root = ET.fromstring(content)
            return self._xml_to_dict(root)
        else:
            raise ValueError(f"Cannot parse format: {format}")
    
    def _convert(self, data: Any, to_fmt: str, options: Dict) -> Any:
        """Convert between formats."""
        if to_fmt == "json":
            return json.dumps(data, indent=2)
        elif to_fmt == "csv":
            if isinstance(data, list) and len(data) > 0:
                output = StringIO()
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
                return output.getvalue()
            return ""
        elif to_fmt == "yaml" and YAML_AVAILABLE:
            return yaml.dump(data, default_flow_style=False)
        elif to_fmt == "parquet" and PARQUET_AVAILABLE and PANDAS_AVAILABLE:
            df = pd.DataFrame(data)
            # Return as base64 encoded bytes
            import base64
            buffer = StringIO()
            df.to_parquet(buffer, index=False)
            return base64.b64encode(buffer.getvalue().encode()).decode()
        elif to_fmt == "excel" and PANDAS_AVAILABLE:
            df = pd.DataFrame(data)
            output = StringIO()
            df.to_excel(output, index=False)
            return output.getvalue()
        else:
            raise ValueError(f"Cannot convert to: {to_fmt}")
    
    def _filter_data(self, data: List[Dict], query: Optional[str], options: Dict) -> List[Dict]:
        """Filter data by query conditions."""
        if not query or not isinstance(data, list):
            return data
        
        # Simple query parser: "column>value", "column=value", etc.
        results = []
        for row in data:
            if self._matches_query(row, query):
                results.append(row)
        
        return results
    
    def _matches_query(self, row: Dict, query: str) -> bool:
        """Check if row matches simple query."""
        # Support: "age>18", "name=John", "status!=inactive"
        for condition in query.split(","):
            condition = condition.strip()
            if ">" in condition:
                col, val = condition.split(">", 1)
                if not (str(row.get(col.strip(), 0)) > val):
                    return False
            elif "<" in condition:
                col, val = condition.split("<", 1)
                if not (str(row.get(col.strip(), 0)) < val):
                    return False
            elif "!=" in condition:
                col, val = condition.split("!=", 1)
                if str(row.get(col.strip(), "")) == val:
                    return False
            elif "=" in condition:
                col, val = condition.split("=", 1)
                if str(row.get(col.strip(), "")) != val:
                    return False
        return True
    
    def _aggregate(self, data: List[Dict], options: Dict) -> Dict[str, Any]:
        """Aggregate data."""
        if not PANDAS_AVAILABLE or not isinstance(data, list):
            return {"error": "Pandas required for aggregation"}
        
        df = pd.DataFrame(data)
        group_by = options.get("group_by")
        agg_func = options.get("function", "sum")  # sum, count, mean, max, min
        
        if group_by and group_by in df.columns:
            result = df.groupby(group_by).agg(agg_func).reset_index()
            return result.to_dict("records")
        else:
            # Global aggregation
            return {
                "count": len(df),
                "sum": df.sum().to_dict() if agg_func == "sum" else None,
                "mean": df.mean().to_dict() if agg_func == "mean" else None,
            }
    
    def _sort(self, data: List[Dict], options: Dict) -> List[Dict]:
        """Sort data."""
        if not isinstance(data, list):
            return data
        
        sort_by = options.get("by")
        reverse = options.get("descending", False)
        
        if sort_by:
            return sorted(data, key=lambda x: x.get(sort_by, ""), reverse=reverse)
        return data
    
    def _deduplicate(self, data: List[Dict], options: Dict) -> List[Dict]:
        """Remove duplicates."""
        if not isinstance(data, list):
            return data
        
        by_key = options.get("by")  # Column to check for duplicates
        seen = set()
        results = []
        
        for row in data:
            key = str(row.get(by_key, row)) if by_key else str(row)
            if key not in seen:
                seen.add(key)
                results.append(row)
        
        return results
    
    def _flatten(self, data: Any, options: Dict) -> Any:
        """Flatten nested structures."""
        separator = options.get("separator", ".")
        
        def flatten(obj, prefix=""):
            items = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{prefix}{separator}{k}" if prefix else k
                    if isinstance(v, (dict, list)):
                        items.extend(flatten(v, new_key).items())
                    else:
                        items.append((new_key, v))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    new_key = f"{prefix}{separator}{i}" if prefix else str(i)
                    if isinstance(v, (dict, list)):
                        items.extend(flatten(v, new_key).items())
                    else:
                        items.append((new_key, v))
            return dict(items)
        
        if isinstance(data, list):
            return [flatten(item) for item in data]
        return flatten(data)
    
    def _xml_to_dict(self, element: ET.Element) -> Any:
        """Convert XML element to dict."""
        result = {}
        
        # Attributes
        if element.attrib:
            result["@attributes"] = element.attrib
        
        # Children
        children = list(element)
        if children:
            child_dict = {}
            for child in children:
                child_data = self._xml_to_dict(child)
                if child.tag in child_dict:
                    if not isinstance(child_dict[child.tag], list):
                        child_dict[child.tag] = [child_dict[child.tag]]
                    child_dict[child.tag].append(child_data)
                else:
                    child_dict[child.tag] = child_data
            result.update(child_dict)
        
        # Text content
        text = element.text.strip() if element.text else ""
        if text:
            if result:
                result["#text"] = text
            else:
                return text
        
        return result if result else None


data_transform_tool = DataTransformTool()

# Alias required by ToolFactory.load_tool() dynamic loader
tool_instance = data_transform_tool