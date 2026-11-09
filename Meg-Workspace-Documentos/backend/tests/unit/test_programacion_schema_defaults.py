from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "app"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_programacion_sources_avoid_shared_mutable_defaults():
    programacion_schema = _read("schemas/programacion.py")
    programacion_api = _read("api/v1/programacion.py")
    presupuesto_schema = _read("schemas/presupuesto.py")
    presupuesto_api = _read("api/v1/presupuestos.py")

    assert "predecesoras: Optional[List[str]] = Field(default_factory=list)" in programacion_schema
    assert "actividades: Optional[List[ActividadCreate]] = Field(default_factory=list)" in programacion_schema
    assert "predecesoras: List[str] = Field(default_factory=list)" in programacion_api
    assert "dependencias_tipo: Optional[dict] = Field(default_factory=dict)" in programacion_api
    assert "metadatos: Optional[dict] = Field(default_factory=dict)" in programacion_api
    assert "partidas: Optional[List[PartidaCreate]] = Field(default_factory=list)" in presupuesto_schema
    assert "insumos: Optional[List[InsumoCosteoInput]] = Field(default_factory=list)" in presupuesto_api
    assert "conceptos: Optional[List[ConceptoCosteoInput]] = Field(default_factory=list)" in presupuesto_api
    assert "insumos: List[InsumoOut] = Field(default_factory=list)" in presupuesto_api
    assert "conceptos: List[ConceptoOut] = Field(default_factory=list)" in presupuesto_api
    assert "partidas: List[PartidaOut] = Field(default_factory=list)" in presupuesto_api
