from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.run_seeds import run_seed


def test_app_startup_does_not_run_seeds():
    """Garante que o boot do container (FastAPI startup) não executa seeds no banco."""
    with patch("app.config.seeds.sync_all_seeds") as mock_sync_seeds:
        test_app = create_app()
        with TestClient(test_app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
        mock_sync_seeds.assert_not_called()


def test_run_seed_executes_sync_all_seeds_on_deploy():
    """Garante que o script explícito de deploy (app.run_seeds) executa sync_all_seeds."""
    mock_session = MagicMock()
    with (
        patch("app.run_seeds.SessionLocal", return_value=mock_session),
        patch("app.run_seeds.sync_all_seeds") as mock_sync_seeds,
    ):
        run_seed()
        mock_sync_seeds.assert_called_once_with(mock_session)
        mock_session.close.assert_called_once()

