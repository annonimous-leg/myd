# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor OCR para extracción de metrados de planos y documentos técnicos.
Soporta: imágenes (PNG, JPG, TIFF), PDFs escaneados, planos arquitectónicos.
"""
import io
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

import numpy as np
from PIL import Image
import cv2

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from app.core.errors import MegalodonException, ErrorCode


@dataclass
class MetradoExtraido:
    """Metrado extraído de un documento."""
    concepto: str
    descripcion: str
    unidad: str
    cantidad: float
    confianza: float
    pagina: int
    bbox: Tuple[int, int, int, int]
    texto_original: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concepto": self.concepto,
            "descripcion": self.descripcion,
            "unidad": self.unidad,
            "cantidad": self.cantidad,
            "confianza": self.confianza,
            "pagina": self.pagina,
            "bbox": self.bbox,
            "texto_original": self.texto_original,
        }


@dataclass
class ResultadoOCR:
    """Resultado completo de extracción OCR."""
    documento_id: str
    total_metrados: int
    confianza_promedio: float
    metrados: List[MetradoExtraido]
    texto_completo: str
    paginas_procesadas: int
    errores: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "documento_id": self.documento_id,
            "total_metrados": self.total_metrados,
            "confianza_promedio": self.confianza_promedio,
            "metrados": [m.to_dict() for m in self.metrados],
            "paginas_procesadas": self.paginas_procesadas,
            "errores": self.errores,
        }


class MotorOCRMetrados:
    """
    Motor de OCR para extracción de metrados de planos de construcción.

    Pipeline:
    1. Preprocesamiento (binarización, deskew, denoising)
    2. OCR con Tesseract (spa)
    3. Detección de tablas de cuantificación
    4. Extracción de conceptos, unidades y cantidades
    5. Validación y normalización
    """

    UNIDADES_CONSTRUCCION = [
        "m3", "m2", "m", "ml", "kg", "t", "pza", "jgo", "par", "l", "gl", "hr", "dia",
        "m3-km", "m2-m", "m3-m", "ml-m", "m3-hr", "m2-hr",
        "m\u00b2", "m\u00b3", "m\u00b3-km", "m\u00b2-m",
    ]

    PATRON_CANTIDAD = re.compile(
        r"(?P<cantidad>\d{1,8}(?:[.,]\d{1,4})?)\s*(?P<unidad>" +
        "|".join(re.escape(u) for u in UNIDADES_CONSTRUCCION) +
        r")",
        re.IGNORECASE
    )

    PATRON_CONCEPTO = re.compile(
        r"(?P<clave>[A-Z0-9\-]{3,20})\s*[\-\.]?\s*(?P<descripcion>.{10,200})",
        re.IGNORECASE
    )

    def __init__(self, tesseract_cmd: Optional[str] = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        if not TESSERACT_AVAILABLE:
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                "Tesseract OCR no está instalado. Instalar: apt-get install tesseract-ocr tesseract-ocr-spa",
            )

    def preprocesar_imagen(self, imagen: np.ndarray) -> np.ndarray:
        """Preprocesa imagen para mejorar OCR."""
        if len(imagen.shape) == 3:
            gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        else:
            gray = imagen.copy()

        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        deskewed = self._deskew(binary)
        return deskewed

    def _deskew(self, imagen: np.ndarray) -> np.ndarray:
        """Corrige inclinación de la imagen."""
        coords = np.column_stack(np.where(imagen > 0))
        if len(coords) < 100:
            return imagen

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        if abs(angle) < 0.5:
            return imagen

        (h, w) = imagen.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(imagen, M, (w, h),
                                  flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
        return rotated

    def detectar_tablas(self, imagen: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detecta regiones de tabla en la imagen."""
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))

        horizontal_lines = cv2.morphologyEx(imagen, cv2.MORPH_OPEN, horizontal_kernel)
        vertical_lines = cv2.morphologyEx(imagen, cv2.MORPH_OPEN, vertical_kernel)

        table_structure = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)
        contours, _ = cv2.findContours(table_structure, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        tablas = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 200 and h > 100:
                tablas.append((x, y, w, h))

        return tablas

    def extraer_texto(self, imagen: np.ndarray, lang: str = "spa") -> Tuple[str, List[Dict]]:
        """Extrae texto de imagen con Tesseract."""
        custom_config = r"--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,-()/\s"

        try:
            data = pytesseract.image_to_data(
                imagen, lang=lang, config=custom_config,
                output_type=pytesseract.Output.DICT
            )

            texto = pytesseract.image_to_string(imagen, lang=lang, config=custom_config)

            palabras = []
            for i in range(len(data["text"])):
                if int(data["conf"][i]) > 30:
                    palabras.append({
                        "texto": data["text"][i],
                        "confianza": int(data["conf"][i]),
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "w": data["width"][i],
                        "h": data["height"][i],
                    })

            return texto, palabras

        except Exception as e:
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                f"Error en OCR: {str(e)}",
            )

    def parsear_metrados(self, texto: str, palabras: List[Dict], pagina: int = 1) -> List[MetradoExtraido]:
        """Parsea texto OCR para extraer metrados de construcción."""
        metrados = []
        lineas = texto.split("\n")

        for i, linea in enumerate(lineas):
            linea = linea.strip()
            if not linea or len(linea) < 10:
                continue

            match_cantidad = self.PATRON_CANTIDAD.search(linea)
            if not match_cantidad:
                continue

            cantidad_str = match_cantidad.group("cantidad").replace(",", "")
            try:
                cantidad = float(cantidad_str)
            except ValueError:
                continue

            unidad = match_cantidad.group("unidad").lower()

            match_concepto = self.PATRON_CONCEPTO.search(linea)
            if match_concepto:
                concepto = match_concepto.group("clave")
                descripcion = match_concepto.group("descripcion").strip()
            else:
                concepto = f"CON-{len(metrados)+1:03d}"
                descripcion = re.sub(self.PATRON_CANTIDAD, "", linea).strip()
                descripcion = re.sub(r"^[\s\-\.]+", "", descripcion)

            confianza = 70.0
            bbox = (0, i * 30, 500, 30)

            metrado = MetradoExtraido(
                concepto=concepto,
                descripcion=descripcion[:200],
                unidad=unidad,
                cantidad=cantidad,
                confianza=confianza,
                pagina=pagina,
                bbox=bbox,
                texto_original=linea,
            )
            metrados.append(metrado)

        return metrados

    def procesar_imagen(self, image_bytes: bytes, documento_id: str, pagina: int = 1) -> ResultadoOCR:
        """Procesa una imagen completa para extracción de metrados."""
        imagen = np.array(Image.open(io.BytesIO(image_bytes)))
        preprocesada = self.preprocesar_imagen(imagen)
        texto, palabras = self.extraer_texto(preprocesada)
        tablas = self.detectar_tablas(preprocesada)
        metrados = self.parsear_metrados(texto, palabras, pagina)

        confianza_promedio = (
            sum(m.confianza for m in metrados) / len(metrados)
            if metrados else 0.0
        )

        return ResultadoOCR(
            documento_id=documento_id,
            total_metrados=len(metrados),
            confianza_promedio=round(confianza_promedio, 2),
            metrados=metrados,
            texto_completo=texto,
            paginas_procesadas=1,
        )

    def procesar_pdf(self, pdf_bytes: bytes, documento_id: str, dpi: int = 300) -> ResultadoOCR:
        """Procesa un PDF escaneado para extracción de metrados."""
        try:
            from pdf2image import convert_from_bytes
        except ImportError:
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                "pdf2image no instalado. Instalar: pip install pdf2image",
            )

        imagenes = convert_from_bytes(pdf_bytes, dpi=dpi)

        todos_metrados = []
        texto_completo = ""
        errores = []

        for i, imagen in enumerate(imagenes):
            try:
                buffer = io.BytesIO()
                imagen.save(buffer, format="PNG")
                image_bytes = buffer.getvalue()

                resultado_pagina = self.procesar_imagen(
                    image_bytes, documento_id, pagina=i + 1
                )

                todos_metrados.extend(resultado_pagina.metrados)
                texto_completo += f"\n--- Página {i+1} ---\n" + resultado_pagina.texto_completo

            except Exception as e:
                errores.append(f"Error en página {i+1}: {str(e)}")

        confianza_promedio = (
            sum(m.confianza for m in todos_metrados) / len(todos_metrados)
            if todos_metrados else 0.0
        )

        return ResultadoOCR(
            documento_id=documento_id,
            total_metrados=len(todos_metrados),
            confianza_promedio=round(confianza_promedio, 2),
            metrados=todos_metrados,
            texto_completo=texto_completo,
            paginas_procesadas=len(imagenes),
            errores=errores,
        )

    def procesar_documento(self, file_bytes: bytes, filename: str, documento_id: str) -> ResultadoOCR:
        """Procesa cualquier tipo de documento (imagen o PDF)."""
        extension = Path(filename).suffix.lower()

        if extension in [".pdf"]:
            return self.procesar_pdf(file_bytes, documento_id)
        elif extension in [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]:
            return self.procesar_imagen(file_bytes, documento_id)
        else:
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                f"Formato no soportado: {extension}",
                details={"formatos_soportados": [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]},
            )
