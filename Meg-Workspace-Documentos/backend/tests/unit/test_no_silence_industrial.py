"""Tests industriales para verificar que los silencios fueron eliminados.

Verifica:
- BIM: excepciones se loguean, no se tragan
- CPM: StopIteration se loguea con contexto
- Feodo: excepciones se propagan, no se retornan defaults silenciosos
"""
import pytest
from unittest.mock import MagicMock, patch
import structlog


class TestBIMNoSilence:
    def test_container_read_logs_warning(self):
        """Verificar que el código de BIM tiene logger.warning en except."""
        import ast
        with open("app/engines/bim/motor_bim.py", "r") as f:
            tree = ast.parse(f.read())

        found_logging = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Buscar logger.warning en el cuerpo del except
                for stmt in node.body:
                    stmt_str = ast.dump(stmt)
                    if "logger.warning" in stmt_str or "logger" in stmt_str and "warning" in stmt_str:
                        found_logging = True
                        break
        assert found_logging, "BIM debe tener logger.warning en bloques except"

    def test_no_bare_pass_in_except(self):
        """Verificar que no hay 'pass' solo dentro de except Exception."""
        import ast
        with open("app/engines/bim/motor_bim.py", "r") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                for stmt in node.body:
                    if isinstance(stmt, ast.Pass):
                        # Si hay pass, debe haber algo más en el bloque (logging)
                        assert len(node.body) > 1, "Except con pass debe tener logging adicional"


class TestCPMNoSilence:
    def test_stop_iteration_logs_error(self):
        """Verificar que CPM tiene logger.error en StopIteration."""
        import ast
        with open("app/engines/programacion/cpm.py", "r") as f:
            content = f.read()

        assert "logger.error" in content, "CPM debe usar logger.error"
        assert "cpm_predecesora_no_encontrada" in content, "CPM debe tener identificador de error específico"

    def test_no_bare_pass_in_stop_iteration(self):
        """Verificar que no hay pass solo después de StopIteration."""
        import ast
        with open("app/engines/programacion/cpm.py", "r") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if any(isinstance(t, ast.Name) and t.id == "StopIteration" for t in ([node.type] if not isinstance(node.type, ast.Tuple) else node.type.elts)):
                    for stmt in node.body:
                        if isinstance(stmt, ast.Pass):
                            assert len(node.body) > 1, "StopIteration con pass debe tener logging"


class TestFeodoNoSilence:
    def test_feodo_marks_unavailable_instead_of_reporting_clean_feed(self):
        """Una caída sin respaldo debe distinguirse de un feed vivo vacío."""
        from tezcatlipoca.services.malware.feodo_tracker import FeodoTrackerClient

        client = FeodoTrackerClient()
        client._feed_cache = MagicMock()
        client._feed_cache.load.return_value = None
        with patch(
            "tezcatlipoca.services.malware.feodo_tracker.sync_get",
            side_effect=RuntimeError("network down"),
        ):
            assert client.fetch() == []
        assert client.last_status == "unavailable"
        client._feed_cache.load.assert_called_once_with("feodo_tracker_raw")

    def test_no_silent_pass_comment(self):
        """Verificar que no queda el comentario de silencio."""
        import ast
        with open("tezcatlipoca/services/malware/feodo_tracker.py", "r") as f:
            content = f.read()

        assert "Silently fail" not in content, "No debe quedar comentario de silencio"
        assert "return defaults" not in content, "No debe retornar defaults en silencio"
