import time
from unittest.mock import MagicMock, patch
from backend.services.db_maintenance import DatabaseMaintenanceService


class MockModel:
    """Mock model class for testing with id attribute."""
    id = MagicMock()
    created_at = MagicMock()
    updated_at = MagicMock()
    status = MagicMock()


def test_batch_delete_splits_large_delete_into_batches():
    """Verify _batch_delete helper splits large deletes into multiple transactions."""
    mock_db = MagicMock()
    
    # Mock the query chain for ID fetching (db.query(model.id))
    mock_id_query = MagicMock()
    mock_id_filter = MagicMock()
    mock_id_limit = MagicMock()
    
    # Simulate 2500 rows returned in 3 batches: 1000, 1000, 500
    batch1 = [(i,) for i in range(1, 1001)]
    batch2 = [(i,) for i in range(1001, 2001)]
    batch3 = [(i,) for i in range(2001, 2501)]
    mock_id_limit.all.side_effect = [batch1, batch2, batch3, []]
    mock_id_filter.limit.return_value = mock_id_limit
    mock_id_query.filter.return_value = mock_id_filter
    
    # Mock the delete chain (db.query(model)) - return actual batch sizes
    mock_delete_query = MagicMock()
    mock_delete_filter = MagicMock()
    # Delete returns match the ID batch sizes: 1000, 1000, 500
    mock_delete_filter.delete.side_effect = [1000, 1000, 500]
    mock_delete_query.filter.return_value = mock_delete_filter
    
    # Track which query is being used - check if querying model.id or model
    def query_side_effect(model_class):
        if model_class is MockModel.id:
            return mock_id_query
        else:
            return mock_delete_query
    
    mock_db.query.side_effect = query_side_effect
    
    # Call the helper with MockModel class and string filter
    deleted = DatabaseMaintenanceService._batch_delete(
        mock_db, MockModel, "created_at < cutoff", batch_size=1000, sleep=0
    )
    
    assert deleted == 2500  # Sum of actual deleted rows
    assert mock_db.commit.call_count == 3  # One commit per batch
    assert mock_db.query.call_count == 6   # 3 ID fetches + 3 deletes


def test_batch_delete_respects_batch_size_and_sleep():
    """Verify batch size and sleep are configurable."""
    mock_db = MagicMock()
    
    # Mock the query chain for ID fetching
    mock_id_query = MagicMock()
    mock_id_filter = MagicMock()
    mock_id_limit = MagicMock()
    
    batch1 = [(i,) for i in range(1, 501)]
    batch2 = [(i,) for i in range(501, 1001)]
    mock_id_limit.all.side_effect = [batch1, batch2, []]
    mock_id_filter.limit.return_value = mock_id_limit
    mock_id_query.filter.return_value = mock_id_filter
    
    # Mock the delete chain - return actual batch sizes
    mock_delete_query = MagicMock()
    mock_delete_filter = MagicMock()
    mock_delete_filter.delete.side_effect = [500, 500]
    mock_delete_query.filter.return_value = mock_delete_filter
    
    def query_side_effect(model_class):
        if model_class is MockModel.id:
            return mock_id_query
        else:
            return mock_delete_query
    
    mock_db.query.side_effect = query_side_effect
    
    with patch("time.sleep") as mock_sleep:
        deleted = DatabaseMaintenanceService._batch_delete(
            mock_db, MockModel, "created_at < cutoff", batch_size=500, sleep=0.05
        )
    
    assert deleted == 1000
    # Implementation sleeps after each batch where deleted == batch_size
    # For 2 full batches of 500, it sleeps twice (after each batch)
    assert mock_sleep.call_count == 2
    mock_sleep.assert_called_with(0.05)
    mock_id_filter.limit.assert_called_with(500)


def test_batch_delete_empty_result_returns_zero():
    """Verify _batch_delete returns 0 when no rows match."""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_limit = MagicMock()
    
    mock_limit.all.return_value = []
    mock_filter.limit.return_value = mock_limit
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query
    
    deleted = DatabaseMaintenanceService._batch_delete(
        mock_db, MockModel, "created_at < cutoff", batch_size=1000, sleep=0
    )
    
    assert deleted == 0
    mock_db.commit.assert_not_called()


def test_cleanup_stale_data_uses_batched_delete_for_audit_logs():
    """Verify cleanup_stale_data calls batched delete for audit_logs."""
    from backend.models.entities.audit import AuditLog
    from backend.models.entities.task import Task
    
    with patch.object(DatabaseMaintenanceService, "_batch_delete") as mock_batch:
        mock_batch.return_value = 100
        
        # Mock the db context manager
        with patch("backend.services.db_maintenance.get_db_context") as mock_ctx:
            mock_db = MagicMock()
            mock_ctx.return_value.__enter__.return_value = mock_db
            
            # Mock constitution query to return empty list
            mock_constitution_query = MagicMock()
            mock_constitution_query.order_by.return_value.all.return_value = []
            mock_db.query.return_value = mock_constitution_query
            
            # Run one iteration of cleanup (mock the sleep to exit loop)
            import asyncio
            async def run_once():
                task = asyncio.create_task(DatabaseMaintenanceService.cleanup_stale_data())
                await asyncio.sleep(0.01)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            asyncio.run(run_once())
            
            # Verify batched delete was called for audit_logs
            assert mock_batch.called
            # First call should be for AuditLog
            first_call_args = mock_batch.call_args_list[0]
            assert first_call_args[0][1] == AuditLog  # model is AuditLog