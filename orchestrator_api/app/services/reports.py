"""
Module Rapports & Exports : CSV et PDF sur une période donnée.

- Les CSV s'ouvrent correctement dans Excel francophone : marque d'ordre des
  octets (sinon « Dépôt » devient « DÃ©pÃ´t ») et point-virgule comme
  séparateur (sinon tout atterrit dans une seule colonne).
- Les valeurs de texte libre ne s'exécutent pas : une justification saisie
  par un développeur et lue par la direction ne doit jamais devenir une
  formule à l'ouverture.

Chaque export renvoie (octets, nom de fichier) ; la réponse HTTP est
l'affaire des routes.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer
from sqlmodel import Session, select

from app.models.audit import AuditLog, verify_chain_integrity
from app.models.pipeline import Pipeline
from app.models.user import User
from app.services import report_style as ui

DEFAULT_PERIOD = timedelta(days=30)

#: Caractères qui font interpréter une cellule comme une formule par Excel,
#: LibreOffice et Google Sheets.
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """Préfixe apostrophe : la valeur reste lisible, le tableur la traite comme du texte."""
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text.startswith(FORMULA_TRIGGERS) else text


def build_csv(header: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows([[safe_cell(cell) for cell in row] for row in rows])
    return buffer.getvalue().encode("utf-8-sig")


def date_range(from_: date | None, to: date | None) -> tuple[datetime, datetime]:
    """Bornes de la période, les 30 derniers jours par défaut."""
    end = datetime.combine(to, time.max, tzinfo=timezone.utc) if to else datetime.now(timezone.utc)
    if from_:
        start = datetime.combine(from_, time.min, tzinfo=timezone.utc)
    else:
        start = (end - DEFAULT_PERIOD).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


def _fr(moment: datetime) -> str:
    return moment.strftime("%d/%m/%Y %H:%M")


def _pipelines(db: Session, start: datetime, end: datetime) -> list[Pipeline]:
    return db.exec(
        select(Pipeline)
        .where(Pipeline.created_at >= start, Pipeline.created_at <= end)  # type: ignore[arg-type]
        .order_by(Pipeline.created_at)  # type: ignore[arg-type]
    ).all()


def _entries(db: Session, start: datetime, end: datetime) -> list[AuditLog]:
    return db.exec(
        select(AuditLog)
        .where(AuditLog.timestamp >= start, AuditLog.timestamp <= end)  # type: ignore[arg-type]
        .order_by(AuditLog.timestamp)  # type: ignore[arg-type]
    ).all()


def pipelines_csv(db: Session, start: datetime, end: datetime) -> tuple[bytes, str]:
    rows = [
        [p.id, p.repository, p.branch, p.commit_id, p.author, ui.label_for(p.status), _fr(p.created_at)]
        for p in _pipelines(db, start, end)
    ]
    header = ["ID", "Dépôt", "Branche", "Commit", "Auteur", "Statut", "Reçu le (UTC)"]
    return build_csv(header, rows), f"pipelines_{start.date()}_{end.date()}.csv"


def audit_csv(db: Session, start: datetime, end: datetime) -> tuple[bytes, str]:
    rows = [
        [
            e.id, _fr(e.timestamp), e.repository_name, e.developer_username, e.commit_hash, ui.label_for(e.decision),
            e.ai_anomaly_score, e.sonarqube_vulnerabilities, e.approved_by or "", e.four_eyes_approved_by or "", e.justification,
        ]
        for e in _entries(db, start, end)
    ]
    header = [
        "ID", "Horodatage (UTC)", "Dépôt", "Développeur", "Commit", "Décision",
        "Score d'anomalie", "Vulnérabilités", "1re validation", "2de validation", "Justification",
    ]
    return build_csv(header, rows), f"audit_{start.date()}_{end.date()}.csv"


def summary_pdf(db: Session, start: datetime, end: datetime, requested_by: User) -> tuple[bytes, str]:
    """
    Rapport de conformité de la période : synthèse, répartition des décisions,
    détail de chaque dérogation accordée, activité par dépôt, et attestation
    d'intégrité du journal, ce qu'un auditeur vient y chercher.
    """
    pipelines = _pipelines(db, start, end)
    entries = _entries(db, start, end)
    period = f"du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}"

    decisions = Counter(e.decision for e in entries)
    derogations = [e for e in entries if e.decision == "DEROGATION"]

    story: list = [
        Paragraph("Rapport de conformité", ui.TITLE),
        Paragraph(f"Hadi · période {period}", ui.SUBTITLE),
        Spacer(1, 4 * mm),
        Paragraph(
            f"Généré le {ui.generated_at()} à la demande de "
            f"<b>{xml_escape(requested_by.username)}</b> ({ui.label_for(requested_by.role.value)}).",
            ui.SMALL,
        ),
        Spacer(1, 7 * mm),
        ui.key_figures(
            [
                ("Pipelines reçus", str(len(pipelines))),
                ("Décisions prises", str(len(entries))),
                ("Blocages", str(decisions.get("BLOCKED", 0))),
                ("Mises en attente", str(decisions.get("WAITING_HUMAN", 0))),
                ("Dérogations", str(len(derogations))),
            ]
        ),
        Spacer(1, 8 * mm),
    ]

    story += _section_decisions(decisions)
    story += _section_derogations(derogations)
    story += _section_activity(pipelines)
    story.append(_section_integrity(db))

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=ui.PAGE_SIZE,
        leftMargin=ui.MARGIN,
        rightMargin=ui.MARGIN,
        topMargin=ui.MARGIN + 4 * mm,
        bottomMargin=ui.MARGIN + 6 * mm,
        title=f"Rapport de conformité {period}",
        author="Hadi",
        subject="Conformité des déploiements",
    ).build(story, canvasmaker=lambda *args, **kwargs: ui.NumberedCanvas(*args, header=f"Rapport de conformité · {period}", **kwargs))
    return buffer.getvalue(), f"rapport_conformite_{start.date()}_{end.date()}.pdf"


def _section_decisions(decisions: Counter) -> list:
    story = [Paragraph("Répartition des décisions", ui.HEADING)]
    if decisions:
        total = sum(decisions.values())
        rows = [
            [ui.label_for(code), str(count), f"{count * 100 / total:.1f} %"]
            for code, count in sorted(decisions.items(), key=lambda item: -item[1])
        ]
        story.append(
            ui.table(
                [["Décision", "Nombre", "Part"]] + rows,
                widths=[ui.CONTENT_WIDTH * 0.6, ui.CONTENT_WIDTH * 0.2, ui.CONTENT_WIDTH * 0.2],
                align={1: "RIGHT", 2: "RIGHT"},
            )
        )
    else:
        story.append(Paragraph("Aucune décision enregistrée sur la période.", ui.BODY))
    return story + [Spacer(1, 7 * mm)]


def _section_derogations(derogations: list[AuditLog]) -> list:
    story = [
        Paragraph("Dérogations accordées", ui.HEADING),
        Paragraph(
            "Chaque dérogation lève un blocage ou une mise en attente et exige la validation "
            "de deux personnes distinctes (règle des quatre yeux).",
            ui.SMALL,
        ),
        Spacer(1, 3 * mm),
    ]
    if derogations:
        rows = [
            [
                Paragraph(_fr(e.timestamp), ui.CELL_SMALL),
                Paragraph(xml_escape(e.repository_name), ui.CELL),
                # 8 caractères : la convention Git courte, et la colonne tient la valeur sur une ligne.
                Paragraph(xml_escape(e.commit_hash[:8]), ui.CELL_SMALL),
                Paragraph(f"{xml_escape(e.approved_by or '')}<br/>{xml_escape(e.four_eyes_approved_by or '')}", ui.CELL_SMALL),
                Paragraph(xml_escape(e.justification or ""), ui.CELL_SMALL),
            ]
            for e in derogations
        ]
        story.append(
            ui.table(
                [["Date", "Dépôt", "Commit", "Validations", "Justification"]] + rows,
                widths=[ui.CONTENT_WIDTH * w for w in (0.13, 0.19, 0.13, 0.19, 0.36)],
            )
        )
    else:
        story.append(Paragraph("Aucune dérogation accordée sur la période.", ui.BODY))
    return story + [Spacer(1, 7 * mm)]


def _section_activity(pipelines: list[Pipeline]) -> list:
    story = [Paragraph("Activité par dépôt", ui.HEADING)]
    per_repo: dict[str, Counter] = {}
    for pipeline in pipelines:
        per_repo.setdefault(pipeline.repository, Counter())[pipeline.status] += 1

    if per_repo:
        rows = [
            [repository, str(sum(statuses.values())), str(statuses.get("DEPLOYED", 0)), str(statuses.get("BLOCKED", 0)), str(statuses.get("WAITING_HUMAN", 0))]
            for repository, statuses in sorted(per_repo.items(), key=lambda item: -sum(item[1].values()))
        ]
        story.append(
            ui.table(
                [["Dépôt", "Pipelines", "Déployés", "Bloqués", "En attente"]] + rows,
                widths=[ui.CONTENT_WIDTH * w for w in (0.36, 0.16, 0.16, 0.16, 0.16)],
                align={1: "RIGHT", 2: "RIGHT", 3: "RIGHT", 4: "RIGHT"},
            )
        )
    else:
        story.append(Paragraph("Aucun pipeline reçu sur la période.", ui.BODY))
    return story + [Spacer(1, 7 * mm)]


def _section_integrity(db: Session) -> KeepTogether:
    intact, corrupted_id = verify_chain_integrity(db)
    attestation = (
        "La chaîne d'intégrité du journal d'audit a été rejouée intégralement au moment de "
        "la génération de ce rapport : <b>aucune altération détectée</b>."
        if intact
        else f"<b>Rupture de la chaîne d'intégrité détectée à partir de l'entrée n° {corrupted_id}.</b> "
        "Les données de ce rapport doivent être considérées comme non fiables tant que cette "
        "rupture n'est pas expliquée."
    )
    return KeepTogether([Paragraph("Intégrité du journal d'audit", ui.HEADING), Paragraph(attestation, ui.BODY)])
