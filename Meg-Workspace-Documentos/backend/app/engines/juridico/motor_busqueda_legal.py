# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""
Motor de Busqueda Legal Inteligente — Sin IA
- Indice invertido de 969 articulos
- Sinonimos y terminos relacionados
- Scoring por relevancia con ponderacion
- Busqueda por concepto (no solo keywords)
"""

import json
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

class MotorBusquedaLegal:
    """Motor de busqueda en corpus legal con 969 articulos."""

    SINONIMOS = {
        "abandono": ["abandonar", "desistimiento", "renuncia", "retiro", "desercion"],
        "adjudicacion": ["adjudicar", "fallo", "ganador", "seleccion", "asignacion"],
        "adenda": ["convenio modificatorio", "modificacion", "adicional", "suplemento"],
        "anticipo": ["pago anticipado", "adelanto", "prestamo", "financiamiento"],
        "aval": ["garantia", "fianza", "caucion", "respaldo"],
        "bitacora": ["diario", "registro", "control", "seguimiento", "supervision"],
        "cancelar": ["anular", "revocar", "rescindir", "terminar", "concluir"],
        "clausula": ["disposicion", "estipulacion", "condicion", "requisito"],
        "competencia": ["concurso", "licitacion", "invitacion", "procedimiento"],
        "contratista": ["licitante", "proveedor", "contratado", "responsable"],
        "contrato": ["convenio", "acuerdo", "pacto", "documento"],
        "cumplimiento": ["ejecucion", "realizacion", "desarrollo", "implementacion"],
        "desierta": ["fallida", "sin proposiciones", "vacante"],
        "estimacion": ["avance", "pago parcial", "certificacion", "metrado"],
        "finiquito": ["liquidacion", "cierre", "terminacion", "conclusion"],
        "garantia": ["fianza", "aval", "caucion", "respaldo", "seguridad"],
        "imputacion": ["responsabilidad", "sancion", "penalizacion", "castigo"],
        "inconformidad": ["protesta", "queja", "recurso", "apelacion", "revision"],
        "insumos": ["materiales", "recursos", "equipos", "bienes", "productos"],
        "invitacion": ["restringida", "cuando menos tres", "privada", "selectiva"],
        "junta": ["reunion", "sesion", "aclaraciones", "preguntas"],
        "licitacion": ["concurso", "competencia", "proceso", "seleccion"],
        "monto": ["precio", "cantidad", "importe", "valor", "costo", "cuantia"],
        "obra": ["trabajo", "proyecto", "construccion", "ejecucion", "edificacion"],
        "penalizacion": ["sancion", "multa", "castigo", "pena", "resarcimiento"],
        "plazo": ["tiempo", "periodo", "vigencia", "duracion", "termino", "fecha"],
        "procedimiento": ["proceso", "mecanismo", "modalidad", "forma", "metodo"],
        "proposicion": ["oferta", "propuesta", "cotizacion", "presentacion"],
        "recepcion": ["aceptacion", "entrega", "adjudicacion", "toma", "recibo"],
        "recurso": ["inconformidad", "protesta", "queja", "apelacion", "revision"],
        "rescisión": ["rescision", "terminacion", "cancelacion", "anulacion"],
        "responsabilidad": ["obligacion", "deber", "compromiso", "imputacion"],
        "sancion": ["penalizacion", "castigo", "multa", "reprimenda"],
        "sfp": ["secretaria", "funcion publica", "fiscalizacion", "control"],
        "subcontratacion": ["subcontrato", "tercerizacion", "delegacion", "encargo"],
        "supervision": ["vigilancia", "monitoreo", "control", "fiscalizacion"],
        "tiempo adicional": ["prorroga", "extension", "ampliacion", "postergacion"],
        "transparencia": ["informacion publica", "acceso", "disponibilidad"],
        "umbral": ["limite", "tope", "monto maximo", "cota", "franja"],
        "vicios ocultos": ["defectos", "fallas", "imperfecciones", "deficiencias"],
    }

    CATEGORIAS = {
        "abandono_obra": ["abandono", "desistimiento", "retiro", "contratista", "incumplimiento", "penalizacion"],
        "sanciones": ["sancion", "penalizacion", "multa", "sfp", "responsabilidad", "infraccion", "falta"],
        "recursos_inconformidad": ["inconformidad", "recurso", "protesta", "queja", "revision", "apelacion"],
        "garantias": ["garantia", "fianza", "aval", "caucion", "seriedad", "cumplimiento", "vicios"],
        "plazos": ["plazo", "tiempo", "fecha", "calendario", "dias", "habiles", "prorroga"],
        "procedimientos": ["licitacion", "invitacion", "adjudicacion", "directa", "publica", "restringida"],
        "contratos": ["contrato", "convenio", "adenda", "modificatorio", "rescision", "terminacion"],
        "pagos": ["estimacion", "pago", "anticipo", "finiquito", "liquidacion", "monto"],
        "documentos": ["documento", "escrito", "acta", "constancia", "dictamen", "certificado"],
        "evaluacion": ["evaluacion", "calificacion", "puntaje", "criterio", "tecnica", "economica"],
    }

    def __init__(self, corpus_path=None):
        self.corpus = {}
        self.indice = defaultdict(list)
        self.categorias_articulos = defaultdict(list)
        self._loaded = False
        self.corpus_path = corpus_path or Path(__file__).parent.parent.parent / "data" / "legal_corpus" / "corpus_articulos_completo.json"

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._load_corpus()
        self._build_index()
        self._categorize()
        self._loaded = True

    def _load_corpus(self):
        if not self.corpus_path.exists():
            raise FileNotFoundError(f"Corpus no encontrado: {self.corpus_path}")
        raw = self.corpus_path.read_bytes()
        self.corpus_sha256 = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw)
        for ley_name, ley_data in data.items():
            if isinstance(ley_data, dict) and "articulos" in ley_data:
                self.corpus[ley_name] = {
                    "nombre": ley_name,
                    "total": ley_data.get("total_articulos", 0),
                    "articulos": {}
                }
                for num, art_data in ley_data["articulos"].items():
                    self.corpus[ley_name]["articulos"][num] = {
                        "numero": num,
                        "texto": art_data.get("texto", ""),
                        "longitud": art_data.get("longitud", 0),
                        "ley": ley_name,
                    }

    def _build_index(self):
        for ley_name, ley_data in self.corpus.items():
            for num, art in ley_data["articulos"].items():
                texto = art["texto"].lower()
                palabras = set(re.findall(r"\b[a-záéíóúñ]{4,}\b", texto))
                for palabra in palabras:
                    self.indice[palabra].append((ley_name, num, 1))

    def _categorize(self):
        for categoria, palabras_clave in self.CATEGORIAS.items():
            for ley_name, ley_data in self.corpus.items():
                for num, art in ley_data["articulos"].items():
                    texto_lower = art["texto"].lower()
                    score = sum(1 for p in palabras_clave if p in texto_lower)
                    if score >= 2:
                        self.categorias_articulos[categoria].append((ley_name, num, score))
            self.categorias_articulos[categoria].sort(key=lambda x: x[2], reverse=True)

    def _expandir_query(self, query):
        palabras = query.lower().split()
        expandidas = set(palabras)
        for palabra in palabras:
            for termino, sinonimos in self.SINONIMOS.items():
                if palabra == termino or palabra in sinonimos:
                    expandidas.add(termino)
                    expandidas.update(sinonimos)
            if palabra in self.SINONIMOS:
                expandidas.update(self.SINONIMOS[palabra])
        return list(expandidas)

    def _detectar_categoria(self, query):
        query_lower = query.lower()
        for categoria, palabras in self.CATEGORIAS.items():
            if any(p in query_lower for p in palabras):
                return categoria
        return None

    def buscar(self, query, ley=None, fase=None, max_resultados=10):
        self._ensure_loaded()
        if not query.strip():
            return []
        terminos = self._expandir_query(query)
        categoria = self._detectar_categoria(query)
        resultados_scores = defaultdict(int)
        for termino in terminos:
            for ley_name, num, _ in self.indice.get(termino, []):
                if ley and ley_name != ley:
                    continue
                resultados_scores[(ley_name, num)] += 3
        if categoria:
            for ley_name, num, score in self.categorias_articulos.get(categoria, [])[:20]:
                if ley and ley_name != ley:
                    continue
                resultados_scores[(ley_name, num)] += score * 2
        for ley_name, ley_data in self.corpus.items():
            if ley and ley_name != ley:
                continue
            for num, art in ley_data["articulos"].items():
                texto_lower = art["texto"].lower()
                score = sum(2 for t in terminos if t in texto_lower)
                if score > 0:
                    resultados_scores[(ley_name, num)] += score
        query_lower = query.lower()
        for key in list(resultados_scores.keys()):
            ley_name, num = key
            texto = self.corpus[ley_name]["articulos"][num]["texto"].lower()
            if query_lower in texto:
                resultados_scores[key] += 10
        resultados_ordenados = sorted(resultados_scores.items(), key=lambda x: x[1], reverse=True)
        resultados = []
        for (ley_name, num), score in resultados_ordenados[:max_resultados]:
            art = self.corpus[ley_name]["articulos"][num]
            titulo = art["texto"].split("\n")[0][:80]
            if len(titulo) > 80:
                titulo = titulo[:80] + "..."
            resultados.append({
                "ley": ley_name,
                "ley_nombre": ley_name,
                "articulo": num,
                "titulo": titulo,
                "contenido": art["texto"][:500],
                "contenido_completo": art["texto"],
                "score": score,
                "longitud": art["longitud"],
            })
        return resultados

    def obtener_articulo(self, ley, numero):
        self._ensure_loaded()
        ley_map = {
            "laassp": "LAASSP",
            "lopsrm": "LOPSRM",
            "lgra": "LGRA",
            "reglamento_laassp": "Reglamento LAASSP",
            "reglamento_lopsrm": "Reglamento LOPSRM",
        }
        ley_buscar = ley_map.get(ley.lower(), ley)
        if ley_buscar not in self.corpus:
            return None
        art = self.corpus[ley_buscar]["articulos"].get(numero)
        if not art:
            return None
        return {
            "ley": ley_buscar,
            "ley_nombre": ley_buscar,
            "articulo": numero,
            "titulo": art["texto"].split("\n")[0][:100],
            "contenido": art["texto"],
            "longitud": art["longitud"],
        }

    def buscar_por_categoria(self, categoria, max_resultados=10):
        self._ensure_loaded()
        resultados = []
        for ley_name, num, score in self.categorias_articulos.get(categoria, [])[:max_resultados]:
            art = self.corpus[ley_name]["articulos"][num]
            resultados.append({
                "ley": ley_name,
                "ley_nombre": ley_name,
                "articulo": num,
                "titulo": art["texto"].split("\n")[0][:100],
                "contenido": art["texto"][:400],
                "score": score,
            })
        return resultados

    def listar_leyes(self):
        self._ensure_loaded()
        leyes = [
            {"id": "laassp", "nombre": "Ley de Adquisiciones, Arrendamientos y Servicios del Sector Publico", "siglas": "LAASSP", "articulos": 119},
            {"id": "lopsrm", "nombre": "Ley de Obras Publicas y Servicios Relacionados con las Mismas", "siglas": "LOPSRM", "articulos": 133},
            {"id": "lgra", "nombre": "Ley General de Responsabilidades Administrativas", "siglas": "LGRA", "articulos": 229},
            {"id": "reglamento_laassp", "nombre": "Reglamento de la LAASSP", "siglas": "Reglamento LAASSP", "articulos": 193},
            {"id": "reglamento_lopsrm", "nombre": "Reglamento de la LOPSRM", "siglas": "Reglamento LOPSRM", "articulos": 295},
        ]
        return [{**ley, "articulos": len(self.corpus[ley['siglas']]['articulos'])}
                for ley in leyes if ley['siglas'] in self.corpus]

    def cobertura(self):
        """Cobertura de búsqueda; un salto no demuestra ausencia en la norma."""
        self._ensure_loaded()
        documentos = []
        for nombre, ley in self.corpus.items():
            articulos = ley['articulos']
            numeros = {int(n) for n in articulos if n.isdigit()}
            documentos.append({
                'nombre': nombre, 'articulos_segmentados': len(articulos),
                'articulos_consultables': sum(bool(a['texto'].strip()) for a in articulos.values()),
                'conteo_declarado': ley['total'],
                'conteo_declarado_coincide': ley['total'] == len(articulos),
                'numeros_no_segmentados': sorted(set(range(1, max(numeros, default=0) + 1)) - numeros),
            })
        return {'sha256': self.corpus_sha256,
                'total_articulos_consultables': sum(d['articulos_consultables'] for d in documentos),
                'documentos': documentos,
                'documentos_sin_articulos': [d['nombre'] for d in documentos if not d['articulos_consultables']],
                'vigencia_certificada': False,
                'alcance': 'Artículos del corpus local consultados por LEGL; no incluye textos DOF separados ni reglas de automatización'}

    def listar_categorias(self):
        return [
            {"id": "abandono_obra", "nombre": "Abandono de Obra", "descripcion": "Desistimiento, retiro, incumplimiento del contratista"},
            {"id": "sanciones", "nombre": "Sanciones", "descripcion": "Sanciones, multas, responsabilidades administrativas"},
            {"id": "recursos_inconformidad", "nombre": "Recursos de Inconformidad", "descripcion": "Protestas, quejas, apelaciones, revisiones"},
            {"id": "garantias", "nombre": "Garantias", "descripcion": "Fianzas, avales, cauciones, seriedad, cumplimiento"},
            {"id": "plazos", "nombre": "Plazos", "descripcion": "Tiempos, fechas, prorrogas, calendario"},
            {"id": "procedimientos", "nombre": "Procedimientos", "descripcion": "Licitacion, invitacion, adjudicacion directa"},
            {"id": "contratos", "nombre": "Contratos", "descripcion": "Convenios, adendas, rescision, terminacion"},
            {"id": "pagos", "nombre": "Pagos", "descripcion": "Estimaciones, anticipos, finiquitos, liquidacion"},
            {"id": "documentos", "nombre": "Documentos", "descripcion": "Escritos, actas, constancias, dictamenes"},
            {"id": "evaluacion", "nombre": "Evaluacion", "descripcion": "Calificacion, criterios, tecnica, economica"},
        ]
