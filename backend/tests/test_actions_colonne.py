from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.clients.models import Client
from apps.parametres.models import EntreeJournal

User = get_user_model()


class ActionsColonneTests(TestCase):
    """La colonne « Actions » (Modifier / Supprimer / Voir) est rendue sur
    toutes les tables et respecte les permissions de chaque ModelAdmin."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123',
        )
        self.client.force_login(self.admin)

    def test_table_metier_a_boutons_modifier_et_supprimer(self):
        Client.objects.create(nom='Martin', prenom='Paul')
        response = self.client.get('/admin/clients/client/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a class="databtn databtn-edit"')
        self.assertContains(response, '<a class="databtn databtn-delete"')

    def test_page_suppression_accessible(self):
        client = Client.objects.create(nom='Martin', prenom='Paul')
        response = self.client.get(f'/admin/clients/client/{client.pk}/delete/')
        self.assertEqual(response.status_code, 200)

    def test_fichier_audit_lecture_seule_affiche_voir(self):
        EntreeJournal.objects.create(
            action=EntreeJournal.Action.MODIF, section='test',
            cle='cle_test', libelle='entrée de test', utilisateur=self.admin,
        )
        response = self.client.get('/admin/parametres/entreejournal/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a class="databtn databtn-view"')
        self.assertNotContains(response, '<a class="databtn databtn-edit"')
        self.assertNotContains(response, '<a class="databtn databtn-delete"')