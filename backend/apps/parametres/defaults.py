"""Catalogue de référence des paramètres paramétrables du projet.

Source unique pour la console d'administration, la migration initiale et le
rendu des formulaires. Chaque entrée : (section, clé, libellé, type, défaut,
options, aide, ordre).
"""

import json

#: Textes de la page principale, par langue (miroir de l'i18n du frontend).
ACCUEIL_TEXTES = {
    'fr': {
        'eyebrow': 'Fianarantsoa · Routes des Vins',
        'titre': "Lazan'i Betsileo",
        'motsCles': ['Terroir betsileo', 'Livraison 48 h', 'Paiement sécurisé'],
        'ctaCatalogue': 'Voir le catalogue',
        'ctaPromos': 'Promotions',
        'selectionEyebrow': 'Sélection du moment',
        'selectionTitre': 'Sélection du jour',
        'voirCatalogue': 'Tout le catalogue',
    },
    'mg': {
        'eyebrow': 'Fianarantsoa · Lalàn\'ny vin',
        'titre': "Lazan'i Betsileo",
        'motsCles': ['Valin-tany betsileo', 'Fandefasana 48h', 'Fandoavana azo antoka'],
        'ctaCatalogue': 'Hijery ny katalaogy',
        'ctaPromos': 'Fihenam-bidy',
        'selectionEyebrow': 'Safidy ankehitriny',
        'selectionTitre': 'Safidy ny androany',
        'voirCatalogue': 'Kataolozy rehetra',
    },
    'en': {
        'eyebrow': 'Fianarantsoa · Wine Route',
        'titre': "Lazan'i Betsileo",
        'motsCles': ['Betsileo terroir', '48h delivery', 'Secure payment'],
        'ctaCatalogue': 'Browse the catalogue',
        'ctaPromos': 'Promotions',
        'selectionEyebrow': 'Current selection',
        'selectionTitre': 'Selection of the day',
        'voirCatalogue': 'Full catalogue',
    },
}

#: Valeur par défaut du paramètre ``accueil_textes`` (JSON compact).
ACCUEIL_TEXTES_DEFAUT = json.dumps(ACCUEIL_TEXTES, ensure_ascii=False, separators=(',', ':'))

SECTIONS = [
    {
        'code': 'SOCIETE',
        'libelle': 'Société',
        'icone': 'fas fa-building',
        'aide': 'Coordonnées de la boutique sur les tickets et documents.',
    },
    {
        'code': 'VENTES',
        'libelle': 'Ventes',
        'icone': 'fas fa-scale-balanced',
        'aide': 'Paiements, taxes, remises et seuils de stock.',
    },
    {
        'code': 'POS',
        'libelle': 'Caisse',
        'icone': 'fas fa-cash-register',
        'aide': 'Options de caisse et contenu des documents.',
    },
    {
        'code': 'SECURITE',
        'libelle': 'Sécurité',
        'icone': 'fas fa-shield-halved',
        'aide': 'Verrouillage, durée de session et protection du back-office.',
    },
    {
        'code': 'APPEARANCE',
        'libelle': 'Apparence',
        'icone': 'fas fa-palette',
        'aide': 'Thème, accent de couleurs et densité — aperçu en temps réel.',
    },
    {
        'code': 'ACCUEIL',
        'libelle': 'Site',
        'icone': 'fas fa-house',
        'aide': 'Contenu et couleurs de la page principale.',
    },
    {
        'code': 'SYSTEME',
        'libelle': 'Système',
        'icone': 'fas fa-gears',
        'aide': 'Maintenance et durée de conservation des données.',
    },
]

DEFAULTS = [
    # ================= SOCIETE =================
    ('SOCIETE', 'societe_nom', "Nom de la société", 'TEXT', "LAZAN'I BETSILEO", {},
     'Nom affiché en en-tête de document et sur le tableau de bord.', 10),
    ('SOCIETE', 'societe_slogan', 'Slogan', 'TEXT', 'Vins sélectionnés, service premium', {},
     'Texte d’accroche sous le nom.', 20),
    ('SOCIETE', 'societe_adresse', 'Adresse', 'TEXTAREA', 'Isaha, Fianarantsoa, Madagascar', {},
     'Adresse postale affichée sur les documents.', 30),
    ('SOCIETE', 'societe_telephone', 'Téléphone', 'TEXT', '+261 34 00 000 00', {},
     'Numéro de contact public.', 40),
    ('SOCIETE', 'societe_email', 'E-mail de contact', 'EMAIL', 'contact@lazani-betsileo.mg', {},
     'Adresse de contact du service client.', 50),
    ('SOCIETE', 'societe_siret', 'N° enregistrement', 'TEXT', 'TG-LC-2024-000001', {},
     'Identifiant légal / enregistrement commercial.', 60),
    ('SOCIETE', 'societe_devise', 'Devise', 'TEXT', 'Ar', {},
     'Symbole affiché après les montants (Ar, FCFA, €…).', 70),
    ('SOCIETE', 'societe_fonds_caisse', 'Fonds de caisse (entrée de caisse)', 'DECIMAL', '0', {},
     'Capital de départ posé dans le tiroir à chaque ouverture.', 80),
    ('SOCIETE', 'societe_objectif_mensuel', 'Objectif de CA mensuel', 'DECIMAL', '0', {},
     '« 0 » = objectif auto (2× le mois précédent).', 90),

    # ================= VENTES =================
    ('VENTES', 'ventes_seuil_stock_alerte', 'Seuil d’alerte stock par défaut', 'INT', '10', {},
     'Seuil sous lequel un produit passe « stock faible » lors de sa création.', 10),
    ('VENTES', 'ventes_jours_couverture', 'Couverture de réassort (jours)', 'INT', '14', {},
     'Nombre de jours de stock visé pour anticiper un réassort.', 20),
    ('VENTES', 'ventes_remise_max', 'Remise maximale (en %)', 'DECIMAL', '50', {},
     'Plafond appliqué aux remises saisies en caisse.', 30),
    ('VENTES', 'ventes_tva', 'Taux de TVA (en %)', 'DECIMAL', '20', {'min': 0, 'max': 100},
     'Taux de démonstration inspiré des pièces historiques ; confirmez le taux légal applicable avant toute exploitation.', 40),
    ('VENTES', 'ventes_tva_incluse', 'Prix affichés TTC', 'BOOL', '1', {},
     '« 1 » = le prix de vente contient déjà la TVA (elle est extraite du montant). '
     '« 0 » = la TVA s’ajoute au prix.', 45),
    ('VENTES', 'ventes_delai_paiement_jours', 'Délai de paiement des factures (jours)', 'INT', '60',
     {'min': 0, 'max': 3650},
     'Délai de démonstration inspiré des pièces historiques. La date d’échéance est enregistrée sur chaque vente ; un paiement immédiat peut solder la facture avant cette date.',
     46),
    # Les codes font référence à ``Vente.ModePaiement`` : le paramètre ne
    # crée pas de nouveau vocabulaire, il choisit lesquels sont proposés à la
    # caisse et dans quel ordre. Un test verrouille cette correspondance.
    ('VENTES', 'ventes_modes_paiement', 'Modes de paiement acceptés', 'MULTI',
     'ESPECES,MVOLA,ORANGE_MONEY,AIRTEL_MONEY,MOBILE_MONEY,CHEQUE,CARTE,CREDIT', {
        'choix': [
            ['ESPECES', 'Espèces'],
            ['MVOLA', 'Mvola'],
            ['ORANGE_MONEY', 'Orange Money'],
            ['AIRTEL_MONEY', 'Airtel Money'],
            ['MOBILE_MONEY', 'Mobile Money'],
            ['CHEQUE', 'Chèque'],
            ['CARTE', 'Carte bancaire'],
            ['CREDIT', 'Compte client'],
        ],
        'minimum': 1,
     },
     'Cochez les moyens de paiement proposés à la caisse ; l’ordre d’affichage '
     'suit l’ordre des options ci-dessus. Un mode retiré reste utilisable pour '
     'une vente déjà enregistrée, mais plus proposé à la saisie.', 48),
    ('VENTES', 'ventes_arrondi', 'Arrondi de la monnaie', 'CHOICE', '10', {
        'choix': [['1', 'Aucun (au centime près)'], ['10', '10 unités'], ['50', '50 unités'], ['100', '100 unités']]},
     'Arrondi appliqué au montant rendu en espèces.', 50),
    ('VENTES', 'ventes_decimales', 'Décimales affichées', 'CHOICE', '0', {
        'choix': [['0', '0 (entier)'], ['1', '1 décimale'], ['2', '2 décimales']]},
     'Précision d’affichage des montants dans l’interface.', 60),

    # ================= ================ POS =================
    ('POS', 'pos_son', 'Bip sonore à la caisse', 'BOOL', '1', {},
     'Active le bip à l’ajout d’un article (l’utilisateur peut le couper via le bouton du POS).', 10),
    ('POS', 'pos_plein_ecran', 'Plein écran automatique', 'BOOL', '0', {},
     'Ouvre la caisse en plein écran à son démarrage.', 20),
    ('POS', 'pos_alerte_rupture', 'Alerter les ruptures de stock', 'BOOL', '1', {},
     'Affiche la colonne « ruptures » et le bouton de filtrage au POS.', 30),
    ('POS', 'doc_en_tete', 'En-tête des documents', 'TEXTAREA', "LAZAN'I BETSILEO — Cave d'Isaha", {},
     'Ligne affichée en haut des tickets et documents.', 40),
    ('POS', 'doc_pied', 'Pied des documents', 'TEXTAREA', 'Merci de votre visite ! À très vite.', {},
     'Message de remerciement en bas des documents.', 50),

    # ================= SECURITE =================
    ('SECURITE', 'securite_verrouillage_essais', 'Échecs avant verrouillage', 'INT', '5', {},
     'Nombre d’identifiants erronés autorisé avant blocage temporaire.', 10),
    ('SECURITE', 'securite_verrouillage_duree', 'Durée du verrouillage (min)', 'INT', '15', {},
     'Durée pendant laquelle la connexion est suspendue après les échecs.', 20),
    ('SECURITE', 'securite_session_duree', 'Durée de session (heures)', 'INT', '8', {},
     'Durée maximale d’une session « rester connecté », en heures.', 30),
    ('SECURITE', 'securite_alerte_connexion', 'Alerte connexion par e-mail', 'BOOL', '0', {},
     'Préviendrait par e-mail lors d’une connexion sur un nouvel appareil.', 40),

    # ================= APPEARANCE =================
    ('APPEARANCE', 'appearance_mode_defaut', 'Mode par défaut', 'CHOICE', 'clair', {
        'choix': [['clair', 'Clair'], ['sombre', 'Sombre']]},
     'Thème appliqué aux visiteurs sans préférence enregistrée.', 10),
    ('APPEARANCE', 'appearance_accent', 'Accent de couleur', 'CHOICE', 'or', {
        'choix': [['or', 'Or « Cave »'], ['rubis', 'Rubis'], ['ambre', 'Ambre']]},
     'Couleur signature des icônes, focus et éléments interactifs.', 20),
    ('APPEARANCE', 'appearance_densite', 'Densité de l’interface', 'CHOICE', 'confort', {
        'choix': [['confort', 'Confortable'], ['compact', 'Compacte']]},
     'Espacement des listes et formulaires.', 30),

    # ================= ACCUEIL =================
    ('ACCUEIL', 'accueil_textes', 'Textes de la page (JSON)', 'TEXTAREA',
     ACCUEIL_TEXTES_DEFAUT, {'json': True},
     'Textes de la page principale par langue (fr, mg, en) : eyebrow, titre, motsCles, '
     'ctaCatalogue, ctaPromos, selectionEyebrow, selectionTitre, voirCatalogue.', 10),
    ('ACCUEIL', 'accueil_couleur_fond', 'Couleur de fond (hex)', 'TEXT', '#0C0A09', {},
     'Fond de la page principale — noir profond, par exemple #0C0A09.', 20),
    ('ACCUEIL', 'accueil_couleur_accent', 'Couleur d’accent (hex)', 'TEXT', '#C9A227', {},
     'Accent de la page principale — or, par exemple #C9A227 (2 couleurs maximum).', 30),

    # ================= SYSTEME =================
    ('SYSTEME', 'systeme_maintenance', 'Mode maintenance', 'BOOL', '0', {},
     'Bloque le back-office pour le personnel (les superutilisateurs restent admis).', 10),
    ('SYSTEME', 'systeme_journal_retention', 'Rétention du journal (jours)', 'INT', '90', {},
     'Âge maximal des entrées du journal d’activité avant purge.', 20),
    ('SYSTEME', 'systeme_sauvegarde_retention', 'Rétention des sauvegardes (jours)', 'INT', '30', {},
     'Une sauvegarde plus ancienne que ce délai et au-delà des cinq dernières est effacée '
     'à chaque nouvelle sauvegarde.', 30),
]
