"""Backends e-mail maison (développement).

Django ne fournit pas de backend « fichier » nommant les messages en ``.eml`` :
son ``filebased.EmailBackend`` écrit des fichiers ``.log``. Pour les
démonstrations, un fichier ``.eml`` (message RFC 822) s'ouvre directement dans
n'importe quel client de messagerie.
"""
import datetime
import os

from django.core.mail.backends.filebased import EmailBackend


class EmlFileBackend(EmailBackend):
    """Comme ``filebased.EmailBackend``, mais avec l'extension ``.eml``."""

    def _get_filename(self):
        if self._fname is None:
            timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            fname = f'{timestamp}-{abs(id(self))}.eml'
            self._fname = os.path.join(self.file_path, fname)
        return self._fname
