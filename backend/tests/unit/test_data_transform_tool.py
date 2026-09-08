"""
Quick smoke tests for data_transform_tool.
"""
import pytest


def test_data_transform_convert_json_to_csv():
    from backend.tools.data_transform_tool import data_transform_tool

    data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]

    result = asyncio_run(data_transform_tool.execute(
        action="convert",
        data=data,
        input_format="json",
        output_format="csv"
    ))
    assert result["success"] is True
    assert "alice" in result["result"].lower()


def test_data_transform_filter():
    from backend.tools.data_transform_tool import data_transform_tool

    data = [
        {"name": "Alice", "age": 30, "active": True},
        {"name": "Bob", "age": 25, "active": False},
        {"name": "Charlie", "age": 35, "active": True}
    ]

    result = asyncio_run(data_transform_tool.execute(
        action="filter",
        data=data,
        query="age>28",
        input_format="json"
    ))
    assert result["success"] is True
    assert len(result["result"]) >= 2


def test_data_transform_aggregate():
    from backend.tools.data_transform_tool import data_transform_tool

    data = [
        {"category": "A", "value": 10},
        {"category": "A", "value": 20},
        {"category": "B", "value": 30},
    ]

    result = asyncio_run(data_transform_tool.execute(
        action="aggregate",
        data=data,
        options={"group_by": "category", "function": "sum", "field": "value"},
        input_format="json"
    ))
    assert result["success"] is True


def test_data_transform_sort():
    from backend.tools.data_transform_tool import data_transform_tool

    data = [
        {"name": "Charlie", "age": 35},
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]

    result = asyncio_run(data_transform_tool.execute(
        action="sort",
        data=data,
        options={"by": "age", "descending": False},
        input_format="json"
    ))
    assert result["success"] is True
    output = result["result"]
    assert output[0]["name"] == "Bob"
    assert output[2]["name"] == "Charlie"


def test_data_transform_deduplicate():
    from backend.tools.data_transform_tool import data_transform_tool

    data = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 1, "name": "Alice"},
    ]

    result = asyncio_run(data_transform_tool.execute(
        action="deduplicate",
        data=data,
        input_format="json"
    ))
    assert result["success"] is True
    assert len(result["result"]) == 2


def test_data_transform_flatten():
    from backend.tools.data_transform_tool import data_transform_tool

    data = [
        {"user": {"name": "Alice", "address": {"city": "NYC"}}, "orders": [1, 2]},
    ]

    result = asyncio_run(data_transform_tool.execute(
        action="flatten",
        data=data,
        input_format="json"
    ))
    assert result["success"] is True


def test_data_transform_missing_action():
    from backend.tools.data_transform_tool import data_transform_tool

    result = asyncio_run(data_transform_tool.execute(
        action="invalid",
        data=[{"a": 1}]
    ))
    assert result["success"] is False


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)