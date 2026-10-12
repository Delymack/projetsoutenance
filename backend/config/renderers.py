"""Renderers DRF d'export tabulaire (CSV et XLSX).

Les rapports sont lus à l'écran mais sephinventent : ils partent en Excel vers
le comptable, qui ne veut ni CSV à opensur dans Excel ni un point-virgule qui
change selon la locale machine. Le XLSX est donc produit par openpyxl, et le
CSV par le module csv de la stdlib en UTF-8 avec BOM — sans ce BOM, Excel
distingue mal les accents.

Une seule feuille, l'en-tête si la vue le fournit via ``get_export_entetes()``,
puis les lignes. L'ordre des colonnes est celui du premier dictionnaire de
ligne, ce qui évite de maintenir une liste de champs à côté des serializers.
"""
import csv
import datetime as dt
import decimal
import io

from rest_framework.renderers import BaseRenderer

#: Excel ne devine pas l'UTF-8 sans ce marqueur : les accents deviennent illisibles.
BOM = '\ufeff'


def _valeur_cellule(valeur):
    """Rend une valeur lisible par un tableur, sans perdre l'information."""
    if valeur is None:
        return ''
    if isinstance(valeur, (dt.datetime, dt.date, dt.time)):
        return valeur.isoformat()
    if isinstance(valeur, decimal.Decimal):
        # « float(valeur) » éviterait la notation scientifique, mais perd les
        # décimales significatives d'un montant. On garde le texte exact et
        # laisse la colonne typée par le nombre de décimales.
        return float(valeur)
    if isinstance(valeur, (list, tuple, dict)):
        return ', '.join(str(v) for v in valeur)
    return valeur


def _valeurs_lignes(data, cles):
    """Aplatit la réponse DRF en lignes de cellules.

    Accepte une liste de dictionnaires, une structure paginée
    (``{'results': [...]}``) ou un dictionnaire à plat. ``cles`` sert à lire
    les valeurs ; s'il est vide, l'ordre des clés de la première ligne est
    repris, comme pour une vue qui n'a rien déclaré.
    """
    if isinstance(data, dict):
        for conteneur in ('results', 'donnees', 'data', 'lignes'):
            if isinstance(data.get(conteneur), list):
                data = data[conteneur]
                break
        else:
            data = [{k: v for k, v in data.items() if k != 'count'}]
    lignes = []
    cles = list(cles or [])
    for element in data or []:
        if isinstance(element, dict):
            if not cles:
                cles = list(element.keys())
            lignes.append([_valeur_cellule(element.get(cle)) for cle in cles])
        else:
            lignes.append([_valeur_cellule(element)])
    return lignes, cles


def _colonnes(renderer_context):
    """Clés techniques et libellés d'en-tête, selon ce que la vue déclare.

    La vue peut exposer deux points d'extension :

    * ``get_export_entetes()`` — l'ordre des clés, dans l'ordre d'affichage ;
    * ``get_export_libelles(cles)`` — le nom lisible de chaque colonne, pour
      que le tableur ne parle pas ``chiffre_affaires`` à un comptable.

    Les deux sont distincts : les valeurs se lisent par clé, jamais par libellé.
    """
    view = renderer_context.get('view')
    cles = []
    if view is not None and hasattr(view, 'get_export_entetes'):
        cles = list(view.get_export_entetes() or [])
    libelles = list(cles)
    if view is not None and hasattr(view, 'get_export_libelles'):
        provided = list(view.get_export_libelles(cles) or [])
        if provided:
            libelles = provided
    return cles, libelles


def _nom_fichier(renderer_context, defaut, extension):
    """Nom de téléchargement, si la vue en fournit un.

    « export.csv » dans le dossier Téléchargements ne dit rien sur le contenu ;
    une vue qui sait ce qu'elle exporte le dit à la place.
    """
    view = renderer_context.get('view')
    if view is not None and hasattr(view, 'get_export_nom'):
        nom = (view.get_export_nom() or '').strip()
        if nom:
            return f'{nom}.{extension}'
    return defaut


class CSVRenderer(BaseRenderer):
    """Export CSV tabulaire, lisible par Excel en UTF-8."""

    media_type = 'text/csv'
    format = 'csv'
    #: `utf-8` et non `utf-8-sig` : le BOM est écrit en tête de contenu, ce qui
    #: garde un `Content-Type` normal tout en faisant ouvrir le fichier
    #: correctement par Excel.
    charset = 'utf-8'
    filename = 'export.csv'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        cles, libelles = _colonnes(renderer_context)
        lignes, cles = _valeurs_lignes(data, cles)
        if not cles:
            libelles = []

        reponse = renderer_context.get('response')
        if reponse is not None:
            nom = _nom_fichier(renderer_context, self.filename, 'csv')
            reponse['Content-Disposition'] = f'attachment; filename="{nom}"'

        tampon = io.StringIO()
        plume = csv.writer(tampon, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        if libelles:
            plume.writerow(libelles)
        plume.writerows(lignes)
        if isinstance(data, dict) and isinstance(data.get('promotions'), dict):
            plume.writerow([])
            plume.writerow(['Indicateurs du rapport', 'Valeur'])
            for cle, libelle in (
                ('ventes', 'Ventes payées'),
                ('chiffre_affaires', "Chiffre d'affaires"),
                ('panier_moyen', 'Panier moyen'),
                ('stock_unites', 'Stock restant (unités)'),
                ('valeur_stock', 'Valeur du stock'),
            ):
                plume.writerow([libelle, data.get(cle, '')])
            promo = data['promotions']
            plume.writerow([])
            plume.writerow(['Efficacité des promotions', 'Valeur'])
            for cle, libelle in (
                ('ventes', 'Ventes avec promotion'),
                ('lignes', 'Lignes avec promotion'),
                ('remise_accordee', 'Remise accordée'),
                ('chiffre_affaires_net', "Chiffre d'affaires net promotionnel"),
                ('taux_remise_pct', 'Taux de remise (%)'),
            ):
                plume.writerow([libelle, promo.get(cle, '')])
            promotions = promo.get('donnees', [])
            if promotions:
                plume.writerow([])
                plume.writerow(['Promotion', 'Ventes', 'Lignes', 'Remise accordée', "Chiffre d'affaires net"])
                plume.writerows([
                    [
                        item.get('promotion', ''),
                        item.get('ventes', 0),
                        item.get('lignes', 0),
                        item.get('remise_accordee', '0.00'),
                        item.get('chiffre_affaires_net', '0.00'),
                    ]
                    for item in promotions
                ])
        # Sans BOM, Excel lit les accents en charabia.
        return BOM + tampon.getvalue()


class XLSXRenderer(BaseRenderer):
    """Export Excel (.xlsx) via openpyxl, avec une vraie feuille lisible."""

    media_type = (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    format = 'xlsx'
    charset = None
    filename = 'export.xlsx'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        renderer_context = renderer_context or {}
        cles, libelles = _colonnes(renderer_context)
        lignes, cles = _valeurs_lignes(data, cles)
        if not cles:
            libelles = []

        reponse = renderer_context.get('response')
        if reponse is not None:
            nom = _nom_fichier(renderer_context, self.filename, 'xlsx')
            reponse['Content-Disposition'] = f'attachment; filename="{nom}"'

        classeur = Workbook()
        entete_font = Font(bold=True, color='FFFFFF')
        entete_fond = PatternFill('solid', start_color='641B2C', end_color='641B2C')

        def ajouter_feuille(nom, entetes, donnees):
            feuille = classeur.create_sheet(nom)
            if entetes:
                feuille.append(entetes)
                for cellule in feuille[1]:
                    cellule.font = entete_font
                    cellule.fill = entete_fond
                    cellule.alignment = Alignment(vertical='center')
                feuille.freeze_panes = 'A2'
            for ligne in donnees:
                feuille.append(ligne)
            for index, colonne in enumerate(feuille.columns, start=1):
                longueur = max(
                    (len(str(cellule.value)) for cellule in colonne if cellule.value is not None),
                    default=0,
                )
                feuille.column_dimensions[get_column_letter(index)].width = min(
                    max(longueur + 2, 10), 60,
                )
            return feuille

        rapport_complet = isinstance(data, dict) and isinstance(data.get('promotions'), dict)
        if rapport_complet:
            feuille_resume = ajouter_feuille('Synthèse', ['Indicateur', 'Valeur'], [
                ['Période', f"{data.get('debut', '')} — {data.get('fin', '')}"],
                ['Ventes payées', data.get('ventes', 0)],
                ["Chiffre d'affaires", data.get('chiffre_affaires', '0.00')],
                ['Panier moyen', data.get('panier_moyen', '0.00')],
                ['Stock restant (unités)', data.get('stock_unites', 0)],
                ['Valeur du stock', data.get('valeur_stock', '0.00')],
                ['Ventes avec promotion', data['promotions'].get('ventes', 0)],
                ['Remise promotionnelle accordée', data['promotions'].get('remise_accordee', '0.00')],
                ["Chiffre d'affaires net promotionnel", data['promotions'].get('chiffre_affaires_net', '0.00')],
                ['Taux de remise promotionnelle (%)', data['promotions'].get('taux_remise_pct', '0.00')],
            ])
            feuille_resume.sheet_view.showGridLines = False
            ajouter_feuille('Ventes', libelles, lignes)
            promos = data['promotions'].get('donnees', [])
            ajouter_feuille('Promotions', [
                'Promotion', 'Ventes', 'Lignes', 'Remise accordée', "Chiffre d'affaires net",
            ], [[
                item.get('promotion', ''),
                item.get('ventes', 0),
                item.get('lignes', 0),
                item.get('remise_accordee', '0.00'),
                item.get('chiffre_affaires_net', '0.00'),
            ] for item in promos])
            classeur.remove(classeur['Sheet'])
        else:
            classeur.remove(classeur.active)
            ajouter_feuille('Export', libelles, lignes)

        sortie = io.BytesIO()
        classeur.save(sortie)
        return sortie.getvalue()


class PDFRenderer(BaseRenderer):
    """Rapport PDF paginé, avec synthèse, ventes et rendement des promotions."""

    media_type = 'application/pdf'
    format = 'pdf'
    charset = None
    filename = 'rapport.pdf'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        from html import escape

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        renderer_context = renderer_context or {}
        reponse = renderer_context.get('response')
        if reponse is not None:
            nom = _nom_fichier(renderer_context, self.filename, 'pdf')
            reponse['Content-Disposition'] = f'attachment; filename="{nom}"'

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='ReportTitle', parent=styles['Title'], textColor=colors.HexColor('#641B2C'),
            alignment=TA_LEFT, fontSize=18, leading=22, spaceAfter=5 * mm,
        ))
        styles.add(ParagraphStyle(
            name='ReportSection', parent=styles['Heading2'], textColor=colors.HexColor('#641B2C'),
            fontSize=12, leading=15, spaceBefore=4 * mm, spaceAfter=2 * mm,
        ))
        styles.add(ParagraphStyle(
            name='ReportCell', parent=styles['BodyText'], fontSize=8, leading=10,
        ))
        styles.add(ParagraphStyle(
            name='ReportHeader', parent=styles['BodyText'], fontSize=8, leading=10,
            textColor=colors.white, fontName='Helvetica-Bold',
        ))
        styles.add(ParagraphStyle(
            name='ReportSmall', parent=styles['BodyText'], fontSize=8, leading=10,
        ))
        flux = []
        flux.append(Paragraph("Rapports &amp; statistiques", styles['ReportTitle']))
        flux.append(Paragraph(
            f"Période : {escape(str(data.get('debut', '')))} — {escape(str(data.get('fin', '')))}",
            styles['ReportSmall'],
        ))
        flux.append(Spacer(1, 3 * mm))

        synthese = [
            ['Ventes payées', str(data.get('ventes', 0))],
            ["Chiffre d'affaires", str(data.get('chiffre_affaires', '0.00'))],
            ['Panier moyen', str(data.get('panier_moyen', '0.00'))],
            ['Stock restant (unités)', str(data.get('stock_unites', 0))],
            ['Valeur du stock', str(data.get('valeur_stock', '0.00'))],
        ]
        promo = data.get('promotions', {})
        if isinstance(promo, dict):
            synthese.extend([
                ['Ventes avec promotion', str(promo.get('ventes', 0))],
                ['Remise promotionnelle accordée', str(promo.get('remise_accordee', '0.00'))],
                ['Chiffre d’affaires net promotionnel', str(promo.get('chiffre_affaires_net', '0.00'))],
                ['Taux de remise promotionnelle', f"{promo.get('taux_remise_pct', '0.00')} %"],
            ])
        flux.append(Paragraph('Synthèse', styles['ReportSection']))
        flux.append(_pdf_table(Table, TableStyle, synthese, colors, header=False))

        cles, libelles = _colonnes(renderer_context)
        lignes, _ = _valeurs_lignes(data, cles)
        flux.append(Paragraph('Détail des ventes', styles['ReportSection']))
        entetes = [Paragraph(escape(str(valeur)), styles['ReportHeader']) for valeur in libelles]
        tableau_ventes = [entetes] + [
            [Paragraph(escape(str(valeur)), styles['ReportCell']) for valeur in ligne]
            for ligne in lignes
        ]
        if not lignes:
            tableau_ventes.append(
                [Paragraph('Aucune vente sur cette période.', styles['ReportCell'])]
                + [''] * max(len(libelles) - 1, 0)
            )
        flux.append(_pdf_table(Table, TableStyle, tableau_ventes, colors, header=True))

        promotions = promo.get('donnees', []) if isinstance(promo, dict) else []
        if promotions:
            flux.append(Paragraph('Détail des promotions', styles['ReportSection']))
            entetes_promo = [
                'Promotion', 'Ventes', 'Lignes', 'Remise accordée', "Chiffre d'affaires net",
            ]
            tableau_promo = [[
                Paragraph(escape(libelle), styles['ReportHeader']) for libelle in entetes_promo
            ]]
            for item in promotions:
                tableau_promo.append([
                    Paragraph(escape(str(item.get('promotion') or '')), styles['ReportCell']),
                    str(item.get('ventes', 0)),
                    str(item.get('lignes', 0)),
                    str(item.get('remise_accordee', '0.00')),
                    str(item.get('chiffre_affaires_net', '0.00')),
                ])
            flux.append(_pdf_table(Table, TableStyle, tableau_promo, colors, header=True))

        sortie = io.BytesIO()
        document = SimpleDocTemplate(
            sortie, pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm,
            topMargin=12 * mm, bottomMargin=12 * mm, title='Rapports et statistiques',
        )
        document.build(flux)
        return sortie.getvalue()


def _pdf_table(Table, TableStyle, rows, colors, header=False):
    """Applique la charte grenat/or aux tables de rapport PDF."""
    table = Table(rows, repeatRows=1 if header else 0, hAlign='LEFT')
    styles = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#e4d8d1')),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if header:
        styles.extend([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#641B2C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ])
    else:
        styles.append(('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fbf8f5')))
    table.setStyle(TableStyle(styles))
    return table
