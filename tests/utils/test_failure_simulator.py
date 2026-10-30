# tests/utils/test_failure_simulator.py
import pytest
from tests.utils.failure_simulator import FailureSimulator


class TestFailureSimulator:
    def test_patch_http_restores_on_exit(self):
        import httpx
        original = httpx.AsyncClient.request
        sim = FailureSimulator()
        with sim.patch_http(return_value=httpx.Response(500)):
            assert httpx.AsyncClient.request is not original
        assert httpx.AsyncClient.request is original

    def test_patch_db_restores_on_exit(self):
        from sqlalchemy import Engine
        original = Engine.connect
        sim = FailureSimulator()
        with sim.patch_db(side_effect=Exception("DB down")):
            assert Engine.connect is not original
        assert Engine.connect is original

    def test_patch_chroma_restores_on_exit(self):
        import chromadb
        original = chromadb.HttpClient
        sim = FailureSimulator()
        with sim.patch_chroma(side_effect=Exception("Chroma down")):
            assert chromadb.HttpClient is not original
        assert chromadb.HttpClient is original

    def test_patch_s3_restores_on_exit(self):
        import boto3
        original = boto3.client
        sim = FailureSimulator()
        with sim.patch_s3(side_effect=Exception("S3 down")):
            assert boto3.client is not original
        assert boto3.client is original