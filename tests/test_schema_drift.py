from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from api.db import Base


def test_models_match_the_migrated_schema(db_session_rollback):
    ctx = MigrationContext.configure(db_session_rollback.connection())
    diff = compare_metadata(ctx, Base.metadata)
    assert diff == []
