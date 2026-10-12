# backend/apps/accounts/utils.py
import secrets


def generate_code():
    """Code à 6 chiffres imprévisible (CSPRNG).

    ``random`` est un générateur Mersenne Twister, prévisible à partir de
    quelques sorties : inadapté à un secret d'authentification. ``secrets``
    s'appuie sur la source d'entropie du système.
    """
    return f'{secrets.randbelow(1000000):06d}'
