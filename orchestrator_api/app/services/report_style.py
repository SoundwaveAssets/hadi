"""
Charte des documents exportés (PDF).

Un rapport destiné à une direction ou à un auditeur externe se lit comme un
document institutionnel, pas comme une sortie de bibliothèque. La version
précédente utilisait `getSampleStyleSheet()` tel quel : titre Helvetica, corps
Times-Roman, aucune pagination, aucune date de génération, aucun émetteur.

Tout est rassemblé ici pour que les tableaux, les couleurs et la typographie
restent cohérents d'un export à l'autre.
"""
from __future__ import annotations

from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle

# --- Palette ----------------------------------------------------------------
INK = colors.HexColor("#1A1D1F")
INK_SOFT = colors.HexColor("#5A6165")
RULE = colors.HexColor("#D5D9D7")
BAND = colors.HexColor("#F2F4F3")
ACCENT = colors.HexColor("#1D5464")

GOOD = colors.HexColor("#2E6B45")
WARN = colors.HexColor("#9A6410")
BAD = colors.HexColor("#A82128")

#: Teinte associée à chaque décision, pour que la lecture d'un tableau ne
#: dépende pas du déchiffrement d'un identifiant technique.
DECISION_TONE = {
    "AUTO_AUTH": GOOD,
    "DEROGATION": GOOD,
    "DEPLOYED": GOOD,
    "WAITING_HUMAN": WARN,
    "DEROGATION_REQUESTED": WARN,
    "DEROGATION_PENDING": WARN,
    "BLOCKED": BAD,
    "REJECTED_INVALID_SIGNATURE": BAD,
    "REJECTED_UNREGISTERED_REPOSITORY": BAD,
}

#: Libellés lisibles. Un rapport destiné à une direction n'affiche pas
#: `WAITING_HUMAN` en majuscules à souligné.
DECISION_LABEL = {
    "AUTO_AUTH": "Autorisé automatiquement",
    "DEROGATION": "Dérogation accordée",
    "DEROGATION_REQUESTED": "Dérogation demandée",
    "DEROGATION_PENDING": "En attente d'une seconde validation",
    "WAITING_HUMAN": "En attente de validation",
    "BLOCKED": "Bloqué",
    "REJECTED_INVALID_SIGNATURE": "Signature de webhook invalide",
    "REJECTED_UNREGISTERED_REPOSITORY": "Dépôt non enregistré",
    "PENDING": "En cours d'analyse",
    "DEPLOYING": "Déploiement en cours",
    "DEPLOYED": "Déployé",
    "DEPLOY_FAILED": "Échec du déploiement",
    "ANALYSIS_FAILED": "Échec de l'analyse",
    "ANALYSIS_TRIGGER_FAILED": "Échec de déclenchement",
}

PAGE_SIZE = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_SIZE[0] - 2 * MARGIN


def label_for(code: str) -> str:
    return DECISION_LABEL.get(code, code)


# --- Styles de texte --------------------------------------------------------
def _style(name: str, **kwargs) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK, alignment=TA_LEFT)
    base.update(kwargs)
    return ParagraphStyle(name, **base)


TITLE = _style("title", fontName="Helvetica-Bold", fontSize=20, leading=25, spaceAfter=2)
SUBTITLE = _style("subtitle", fontSize=10.5, leading=14, textColor=INK_SOFT)
HEADING = _style("heading", fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=6, spaceAfter=6)
BODY = _style("body", spaceAfter=4)
SMALL = _style("small", fontSize=8.5, leading=11.5, textColor=INK_SOFT)
CELL = _style("cell", fontSize=9, leading=12)
CELL_SMALL = _style("cellSmall", fontSize=8, leading=10.5, textColor=INK_SOFT)


# --- Tableaux ---------------------------------------------------------------
def table(data: list[list], widths: list[float], *, align: dict[int, str] | None = None) -> Table:
    """
    Tableau à l'identité commune : en-tête sombre, lignes alternées, filets
    discrets. `align` permet d'aligner à droite les colonnes de chiffres.
    """
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    for column, how in (align or {}).items():
        commands.append(("ALIGN", (column, 0), (column, -1), how))

    rendered = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    rendered.setStyle(TableStyle(commands))
    return rendered


def key_figures(pairs: list[tuple[str, str]]) -> Table:
    """Bandeau de chiffres clés : la valeur domine, le libellé la commente."""
    values = [[value for _, value in pairs]]
    labels = [[label for label, _ in pairs]]
    width = CONTENT_WIDTH / max(len(pairs), 1)

    # Hauteurs explicites : sans elles, la ligne des valeurs se dimensionne sur
    # la police du tableau et non sur ses 19 points réels, les chiffres
    # débordaient alors sur les libellés de la ligne suivante.
    rendered = Table(
        values + labels, colWidths=[width] * len(pairs), rowHeights=[24, 13], hAlign="LEFT"
    )
    rendered.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 19),
                ("LEADING", (0, 0), (-1, 0), 21),
                ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
                ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
                ("TOPPADDING", (0, 0), (-1, 0), 0),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, 1), 8),
                ("LEADING", (0, 1), (-1, 1), 10),
                ("TEXTCOLOR", (0, 1), (-1, 1), INK_SOFT),
                ("VALIGN", (0, 1), (-1, 1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, 1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return rendered


# --- Habillage de page ------------------------------------------------------
class NumberedCanvas(Canvas):
    """
    Pagination « page X sur Y ».

    Le total n'est connu qu'une fois le document entièrement composé : on
    diffère donc l'écriture des pages jusqu'au `save()` final. Sans cela, un
    rapport de plusieurs pages ne peut pas être cité en référence par un
    auditeur, ce qui est précisément son usage.
    """

    def __init__(self, *args, header: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._header = header
        self._pages: list[dict] = []

    def showPage(self) -> None:  # noqa: N802 - API ReportLab
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._draw_furniture(total)
            super().showPage()
        super().save()

    def _draw_furniture(self, total: int) -> None:
        width, height = PAGE_SIZE

        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)

        # En-tête
        self.line(MARGIN, height - MARGIN + 6 * mm, width - MARGIN, height - MARGIN + 6 * mm)
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(INK_SOFT)
        self.drawString(MARGIN, height - MARGIN + 8 * mm, self._header)

        # Pied de page
        self.line(MARGIN, MARGIN - 4 * mm, width - MARGIN, MARGIN - 4 * mm)
        self.setFont("Helvetica", 8)
        self.setFillColor(INK_SOFT)
        self.drawString(MARGIN, MARGIN - 9 * mm, "Document généré automatiquement par Hadi")
        self.drawRightString(width - MARGIN, MARGIN - 9 * mm, f"Page {self._pageNumber} sur {total}")


def generated_at() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y à %H:%M UTC")
