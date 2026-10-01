"""Piezas comunes de los informes PDF (ReportLab): estilos, tablas, chips de
estado, tarjetas de indicadores y la plantilla de página con encabezado y pie."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, Image, PageTemplate, Paragraph, Spacer, Table, TableStyle

from . import config as C
from .utilidades import fecha_larga, texto_pdf

TINTA = colors.HexColor("#0b0b0b")
TINTA_2 = colors.HexColor("#52514e")
TENUE = colors.HexColor("#898781")
NAVY = colors.HexColor("#1F3B5C")
FONDO = colors.HexColor("#f4f5f7")
LINEA = colors.HexColor("#d9dce1")
ESTADO_COLOR = {"ROJO": colors.HexColor("#d03b3b"), "ÁMBAR": colors.HexColor("#fab219"),
                "VERDE": colors.HexColor("#0ca30c"), "SIN DATO": colors.HexColor("#c3c2b7")}
ESTADO_TEXTO = {"ROJO": "#ffffff", "ÁMBAR": "#0b0b0b", "VERDE": "#0b0b0b", "SIN DATO": "#0b0b0b"}
ESTADO_ETIQUETA = {"ROJO": "Excedido", "ÁMBAR": "Alerta", "VERDE": "Cumple", "SIN DATO": "Sin dato"}
TONO_ESTADO = {"rojo": "ROJO", "ambar": "ÁMBAR", "info": None, "verde": "VERDE"}
PRIORIDAD_ESTADO = {"Alta": "ROJO", "Media": "ÁMBAR", "Baja": None}
ANCHO_UTIL = letter[0] - 3.6 * cm


def estilo(nombre, **kw):
    base = dict(fontName="Helvetica", fontSize=9, leading=12.5, textColor=TINTA, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(nombre, **base)


S = {
    "entidad": estilo("entidad", fontSize=9, textColor=TINTA_2, fontName="Helvetica-Bold"),
    "titulo": estilo("titulo", fontSize=20, leading=24, fontName="Helvetica-Bold", textColor=NAVY),
    "sub": estilo("sub", fontSize=10, textColor=TINTA_2, spaceAfter=10),
    "h1": estilo("h1", fontSize=13, leading=16, fontName="Helvetica-Bold", textColor=NAVY, spaceBefore=4, spaceAfter=6),
    "h2": estilo("h2", fontSize=10, leading=13, fontName="Helvetica-Bold", textColor=TINTA, spaceBefore=6, spaceAfter=3),
    "p": estilo("p", spaceAfter=5),
    "peq": estilo("peq", fontSize=7.5, leading=10, textColor=TINTA_2),
    "kpi_rot": estilo("kpi_rot", fontSize=7.8, leading=10, textColor=TINTA_2),
    "kpi_val": estilo("kpi_val", fontSize=15, leading=19, fontName="Helvetica-Bold"),
    "kpi_sub": estilo("kpi_sub", fontSize=7.5, leading=9.5, textColor=TINTA_2),
    "chip": estilo("chip", fontSize=7, leading=9, fontName="Helvetica-Bold", alignment=1),
    "p1": estilo("p1", fontSize=8.3, leading=10.8),
    "vin": estilo("vin", fontSize=8.4, leading=11, leftIndent=9, bulletIndent=0, spaceAfter=3),
}


def P(texto, est="p"):
    return Paragraph(texto_pdf(str(texto)), S[est] if isinstance(est, str) else est)


def E(texto) -> str:
    return escape(texto_pdf(str(texto)))


def imagen(ruta, ancho=ANCHO_UTIL):
    if ruta is None or not Path(ruta).exists():
        return Spacer(1, 1)
    w, h = ImageReader(str(ruta)).getSize()
    return Image(str(ruta), width=ancho, height=ancho * h / w)


def tabla(datos, anchos, numericas=(), negrita_ultima=False, estados=None, col_estado=None, tam=7.8,
          resaltar=()):
    """Tabla con encabezado azul oscuro, filas alternas y números a la derecha.
    Las celdas de texto se pasan ya escapadas (E) o como Paragraph."""
    numericas = set(numericas)

    def est_celda(j, enc=False, negrita=False):
        return estilo(f"c{int(enc)}{int(negrita)}{int(j in numericas)}{tam}", fontSize=tam, leading=tam * 1.28,
                      alignment=2 if j in numericas else 0,
                      fontName="Helvetica-Bold" if (enc or negrita) else "Helvetica",
                      textColor=colors.white if enc else TINTA)

    filas = [[P(E(c), est_celda(j, enc=True)) for j, c in enumerate(datos[0])]]
    ultima = len(datos) - 1
    for i, fila in enumerate(datos[1:], start=1):
        negrita = (negrita_ultima and i == ultima) or i in resaltar
        filas.append([P(c, est_celda(j, negrita=negrita)) if isinstance(c, str) else c for j, c in enumerate(fila)])
    t = Table(filas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 2.8 if tam > 7.3 else 1.9),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8 if tam > 7.3 else 1.9),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINEA)]
    for i in range(2, len(filas), 2):
        st.append(("BACKGROUND", (0, i), (-1, i), FONDO))
    if negrita_ultima:
        st.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, TINTA_2))
    if estados is not None and col_estado is not None:
        for i, e in enumerate(estados, start=1):
            if e in ESTADO_COLOR:
                st.append(("BACKGROUND", (col_estado, i), (col_estado, i), ESTADO_COLOR[e]))
    t.setStyle(TableStyle(st))
    return t


def chip(estado, texto=None):
    if estado is None:
        return P(f'<font color="#52514e">{texto or "Info"}</font>', "chip")
    return Paragraph(f'<font color="{ESTADO_TEXTO[estado]}">{texto or ESTADO_ETIQUETA[estado]}</font>', S["chip"])


def kpi(rotulo, valor, sub):
    return [P(E(rotulo), "kpi_rot"), P(E(valor), "kpi_val"), P(sub, "kpi_sub")]


def fila_kpis(tiles):
    t = Table([tiles], colWidths=[ANCHO_UTIL / len(tiles)] * len(tiles))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FONDO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBEFORE", (1, 0), (-1, 0), 2, colors.white),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def lista_tono(items, ancho_chip=1.7 * cm):
    """items: lista de (estado o None, etiqueta del chip, texto)."""
    filas, st = [], [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3.2),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA)]
    for i, (est, etiqueta, texto) in enumerate(items):
        filas.append([chip(est, etiqueta), P(texto, "p1")])
        st.append(("BACKGROUND", (0, i), (0, i), ESTADO_COLOR[est] if est else FONDO))
    t = Table(filas, colWidths=[ancho_chip, ANCHO_UTIL - ancho_chip])
    t.setStyle(TableStyle(st))
    return t


def num_der(texto, tam=7.8):
    return P(texto, estilo(f"nd{tam}", fontSize=tam, leading=tam * 1.28, alignment=2))


class Documento(BaseDocTemplate):
    def __init__(self, ruta, r, titulo_informe: str):
        super().__init__(str(ruta), pagesize=letter, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                         topMargin=2.0 * cm, bottomMargin=1.7 * cm,
                         title=f"{titulo_informe} - {r['entidad']['nombre']} - {r['corte']:%Y-%m-%d}",
                         author="Motor de riesgo de crédito")
        self.r, self.titulo_informe = r, titulo_informe
        marco = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="m")
        self.addPageTemplates([PageTemplate(id="todas", frames=[marco], onPage=self._decorar)])

    def _decorar(self, canvas, doc):
        r = self.r
        canvas.saveState()
        ancho, alto = letter
        if doc.page > 1:
            canvas.setFont("Helvetica-Bold", 7.5)
            canvas.setFillColor(NAVY)
            canvas.drawString(1.8 * cm, alto - 1.2 * cm, texto_pdf(r["entidad"]["nombre"]))
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(TINTA_2)
            canvas.drawRightString(ancho - 1.8 * cm, alto - 1.2 * cm,
                                   texto_pdf(f"{self.titulo_informe} | Corte {fecha_larga(r['corte'])}"))
            canvas.setStrokeColor(LINEA)
            canvas.setLineWidth(0.6)
            canvas.line(1.8 * cm, alto - 1.35 * cm, ancho - 1.8 * cm, alto - 1.35 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TENUE)
        marca = f" | {C.MARCA}" if C.MARCA else ""
        canvas.drawString(1.8 * cm, 1.1 * cm, texto_pdf(
            f"Motor de riesgo de crédito v{C.VERSION}{marca} | generado {r['traza']['ejecutado'][:16]}"))
        if r["entidad"].get("demo"):
            canvas.drawString(1.8 * cm, 0.75 * cm, texto_pdf(
                "Demostración: entidad ficticia y datos sintéticos. No corresponde a ninguna entidad real."))
        canvas.drawRightString(ancho - 1.8 * cm, 1.1 * cm, f"Página {doc.page}")
        canvas.restoreState()
