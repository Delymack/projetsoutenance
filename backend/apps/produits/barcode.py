"""
Rendu des codes-barres produits par la caisse, sans dépendance externe.

Deux formats sont utilisés :

* **EAN-13** pour les codes internes attribués par l'application (préfixe GS1
  200 = « usage interne »). C'est le format qu'impriment nativement les
  imprimantes d'étiquettes de commerce, et que lisent toutes les douchettes.
* **Code 128** sous-ensemble B, pour les codes saisis à la main lorsqu'ils ne
  tiennent pas sur 13 chiffres (référence fabricant, lot, référence interne
  courte).

La sortie est un SVG prêt à poser sur une étiquette, sans requête ni police
externe : une seule balise, imprimable par le navigateur.
"""

# ---------------------------------------------------------------------------
# Code 128 (sous-ensemble B)
# ---------------------------------------------------------------------------

# Largeurs des 6 éléments (barre, espace, barre, espace, barre, espace) de chaque
# symbole Code 128, dans l'ordre des valeurs 0 → 106 (STOP = 106).
_PATTERNS_128 = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split()

START_B = 104
STOP = 106

# ---------------------------------------------------------------------------
# EAN-13
# ---------------------------------------------------------------------------

#jeu de 7 modules par chiffre, en symbolic pairs
_EAN_G = ("0100111", "0110011", "0011011", "0100001", "0011101",
          "0111001", "0000101", "0010001", "0001001", "0010111")
_EAN_L = ("0001101", "0011001", "0010011", "0111101", "0100011",
          "0110001", "0101111", "0111011", "0110111", "0001011")
_EAN_R = ("1110010", "1100110", "1101100", "1000010", "1011100",
          "1001110", "1010000", "1000100", "1001000", "1110100")
# Parité des 6 chiffres de gauche,Pilotée par le premier chiffre.
_EAN_PARITE = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
               "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")

EAN_LONGUEUR = 13


# ---------------------------------------------------------------------------
# Contrôle de saisie
# ---------------------------------------------------------------------------

def valider_code(code, min_longueur=4):
    """
    Contrôle qu'un code saisi est encodable. Renvoie le code normalisé, ou
    lève `ValueError` avec un message lisible.

    Les espaces et tabulations internes sont retirés : une douchette qui
    transmet des séparateurs ne doit pas faire rejeter le code.
    """
    code = ''.join(str(code or '').split())
    if not code:
        raise ValueError("Le code-barres ne peut pas être vide.")
    if len(code) < min_longueur:
        raise ValueError(
            f"Le code-barres doit contenir au moins {min_longueur} caractères."
        )
    if code.isdigit() and len(code) == EAN_LONGUEUR:
        return code  # EAN-13 : la clé de contrôle est vérifiée à l'affichage
    if not all(32 <= ord(c) <= 126 for c in code):
        raise ValueError(
            "Le code-barres ne peut contenir que des caractères imprimables "
            "(chiffres, lettres, tirets)."
        )
    return code


def cle_ean13_valide(code):
    """Vrai si les 13 chiffres portent une clé de contrôle EAN-13 correcte."""
    if not (code or '').isdigit() or len(code) != EAN_LONGUEUR:
        return False
    corps = code[:12]
    somme = sum((3 if i % 2 else 1) * int(d) for i, d in enumerate(corps))
    return (10 - somme % 10) % 10 == int(code[12])


# ---------------------------------------------------------------------------
# Encodage
# ---------------------------------------------------------------------------

def _modules_128(code):
    """Largeurs de modules Code 128 sous-ensemble B pour `code`."""
    code = (code or '').strip()
    if not code:
        raise ValueError("Le code-barres ne peut pas être vide.")
    valeurs = []
    for caractere in code:
        position = ord(caractere)
        if not 32 <= position <= 126:
            raise ValueError(
                f"Caractère non encodable en Code 128 sous-ensemble B : {caractere!r}."
            )
        valeurs.append(position - 32)

    somme = START_B
    for position, valeur in enumerate(valeurs, start=1):
        somme += position * valeur
    checksum = somme % 103

    modules = []
    for valeur in [START_B, *valeurs, checksum, STOP]:
        modules.extend(int(v) for v in _PATTERNS_128[valeur])
    return modules


def _modules_ean13(code):
    """Largeurs de modules EAN-13 pour un code à 13 chiffres."""
    if not (code or '').isdigit() or len(code) != EAN_LONGUEUR:
        raise ValueError("Un code EAN-13 compte exactement 13 chiffres.")
    premier = int(code[0])
    modules = [1, 0, 1]
    for position, chiffre in enumerate(code[1:7]):
        modules.extend(int(v) for v in (
            _EAN_L[int(chiffre)] if _EAN_PARITE[premier][position] == 'L'
            else _EAN_G[int(chiffre)]
        ))
    modules.extend(int(v) for v in (0, 1, 0, 1, 0))
    for chiffre in code[7:]:
        modules.extend(int(v) for v in _EAN_R[int(chiffre)])
    modules.extend((1, 0, 1))
    return modules


def modules_du_code(code):
    """
    Largeurs de modules du code, format choisi automatiquement : EAN-13 pour
    un code de 13 chiffres, Code 128 sinon.
    """
    code = (code or '').strip()
    if code.isdigit() and len(code) == EAN_LONGUEUR:
        return _modules_ean13(code)
    return _modules_128(code)


def encoder(code):
    """
    Motifs Code 128 du symbole complet (démarrage, données, checksum, arrêt).

    Conservé pour les tests et le diagnostic : le rendu passe par `modules`.
    """
    code = (code or '').strip()
    valeurs = [ord(c) - 32 for c in code]
    somme = START_B
    for position, valeur in enumerate(valeurs, start=1):
        somme += position * valeur
    return [_PATTERNS_128[v] for v in [START_B, *valeurs, somme % 103, STOP]]


# ---------------------------------------------------------------------------
# Rendu
# ---------------------------------------------------------------------------

def svg(code, hauteur=44, largeur_etiquette=260, afficher_texte=True):
    """
    Retourne un SVG (chaîne) représentant `code`, centré sur une étiquette.

    `largeur_etiquette` est exprimé en unités SVG ; le motif est centré
    horizontalement, comme sur une étiquette adhésive de rayon.
    """
    code = (code or '').strip()
    largueurs = modules_du_code(code)

    largeur_totale = sum(largueurs)
    largeur_svg = largeur_etiquette
    hauteur_totale = hauteur + (16 if afficher_texte else 0)

    largeur_motif = largeur_svg * 0.88
    echelle = largeur_motif / largeur_totale
    decalage = (largeur_svg - largeur_totale * echelle) / 2

    rectangles = []
    position = 0
    for index, module in enumerate(largueurs):
        position += module
        # EAN-13 et Code 128 commencent tous deux par une barre et alternent
        # barre / espace : un élément sur deux est donc une barre.
        if index % 2 == 0:
            x = decalage + (position - module) * echelle
            w = module * echelle
            rectangles.append(f'<rect x="{x:.2f}" y="0" width="{w:.2f}" height="{hauteur}"/>')

    texte = ''
    if afficher_texte:
        texte = (
            f'<text x="{largeur_svg / 2:.0f}" y="{hauteur + 12}" text-anchor="middle" '
            f'font-family="monospace" font-size="12" fill="#000">{_echapper(code)}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur_svg} {hauteur_totale}" '
        f'width="{largeur_svg}" height="{hauteur_totale}" shape-rendering="crispEdges">'
        f'<rect width="{largeur_svg}" height="{hauteur_totale}" fill="#fff"/>'
        f'<g fill="#000">{"".join(rectangles)}</g>{texte}</svg>'
    )


def _echapper(texte):
    return (
        str(texte)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


# Alias de lecture explicite, utilisé par l'admin et la caisse.
code_svg = svg
