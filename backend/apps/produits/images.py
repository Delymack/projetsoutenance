"""Import d'une photo de produit depuis une adresse distante.

Une fiche produit accepte deux façons de fournir son image : joindre un
fichier, ou coller l'adresse d'une photo déjà en ligne. Dans ce second cas le
fichier est rapatrié une fois pour toutes dans ``Produit.image`` : le catalogue
n'a ainsi qu'une seule source d'image, et la photo reste affichée même si le
lien d'origine disparaît.
"""
import io
import os
from urllib.parse import unquote, urlparse

import requests
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

# Une vignette de produit tient largement dans cette taille : au-delà, c'est
# une erreur de saisie ou un fichier qui n'a rien à faire dans le catalogue.
TAILLE_MAX = 5 * 1024 * 1024
DELAI_MAX = 10
# Extension de rangement, d'après le format réellement reconnu dans le fichier
# (et non d'après ce que le serveur d'origine annonce).
EXTENSIONS = {
    'JPEG': '.jpg',
    'PNG': '.png',
    'WEBP': '.webp',
    'GIF': '.gif',
    'AVIF': '.avif',
    'BMP': '.bmp',
    'TIFF': '.tiff',
}


class ImageDistanteInvalide(Exception):
    """Le lien fourni ne mène pas à une image utilisable.

    Le message est destiné à être affiché tel quel sous le champ : il dit ce
    qui n'a pas marché, pas comment le code est écrit.
    """


def telecharger_image(lien):
    """Rapatrie l'image du lien et renvoie ``(nom, contenu)`` pour le champ."""
    try:
        reponse = requests.get(lien, timeout=DELAI_MAX, stream=True)
    except requests.RequestException:
        raise ImageDistanteInvalide("Le lien est injoignable. Vérifiez l'adresse.")

    with reponse:
        if reponse.status_code != 200:
            raise ImageDistanteInvalide(
                f'Le lien répond {reponse.status_code} : aucune image à récupérer.'
            )
        type_contenu = (reponse.headers.get('Content-Type') or '').split(';')[0].strip()
        if not type_contenu.lower().startswith('image/'):
            raise ImageDistanteInvalide('Le lien ne pointe pas vers une image.')
        contenu = _lire(reponse)

    return _nom_fichier(lien, _extension(contenu)), ContentFile(contenu)


def _lire(reponse):
    """Lit le corps de la réponse, en refusant les fichiers trop lourds."""
    morceaux, total = [], 0
    for morceau in reponse.iter_content(64 * 1024):
        total += len(morceau)
        if total > TAILLE_MAX:
            raise ImageDistanteInvalide(
                f"L'image dépasse {TAILLE_MAX // (1024 * 1024)} Mo."
            )
        morceaux.append(morceau)
    contenu = b''.join(morceaux)
    if not contenu:
        raise ImageDistanteInvalide("L'image récupérée est vide.")
    return contenu


def _extension(contenu):
    """Vérifie que le fichier est une image lisible et renvoie son extension."""
    try:
        with Image.open(io.BytesIO(contenu)) as image:
            format_image = (image.format or '').upper()
            image.verify()
    # Pillow signale un fichier illisible de plusieurs façons selon le format.
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageDistanteInvalide(
            "Le fichier récupéré n'est pas une image lisible."
        ) from exc
    return EXTENSIONS.get(format_image, '.jpg')


def _nom_fichier(lien, extension):
    """Nom de rangement : celui du lien, ramené à l'extension du format réel."""
    base = os.path.basename(unquote(urlparse(lien).path))
    nom = os.path.splitext(base)[0][:60]
    return f'{nom or "image"}{extension}'