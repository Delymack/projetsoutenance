/* ============================================================
   WineAdmin — JavaScript pour Formulaires Unifiés
   Assure que le hero header et la grille s'appliquent correctement
   ============================================================ */

(function() {
    'use strict';

    // Attendre que le DOM soit chargé
    document.addEventListener('DOMContentLoaded', function() {
        
        // Vérifier si le hero header existe, sinon le créer pour les formulaires de modification
        const changeForm = document.querySelector('.change-form');
        if (!changeForm) return;

        // Ne pas appliquer si le template a déjà son propre hero (ex: produit création)
        if (changeForm.querySelector('.pd-create-hero')) return;
        if (changeForm.querySelector('.form-hero')) return;

        // Trouver le content-title pour extraire les informations
        const contentTitle = document.querySelector('.app-content-header h3');
        if (!contentTitle) return;

        const titleText = contentTitle.textContent.trim();
        const isAdd = titleText.toLowerCase().includes('ajout');
        const isEdit = titleText.toLowerCase().includes('modification');
        
        if (!isAdd && !isEdit) return;

        // Extraire le nom du modèle
        const entitySpan = contentTitle.querySelector('.form-entity');
        const modelName = entitySpan ? entitySpan.textContent.trim() : 'élément';

        // Créer le hero header
        const heroSection = document.createElement('section');
        heroSection.className = 'form-hero';
        heroSection.setAttribute('aria-labelledby', 'form-title');

        const icon = document.createElement('div');
        icon.className = 'form-hero-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.innerHTML = isAdd ? '<i class="fas fa-plus-circle"></i>' : '<i class="fas fa-pen-nib"></i>';

        const content = document.createElement('div');
        content.className = 'form-hero-content';

        const title = document.createElement('h1');
        title.id = 'form-title';
        title.textContent = isAdd ? `Nouveau ${modelName.toLowerCase()}` : `Modifier ${modelName.toLowerCase()}`;

        const description = document.createElement('p');
        description.textContent = isAdd 
            ? `Remplissez les champs ci-dessous pour créer un nouveau ${modelName.toLowerCase()}. Les champs marqués d'un astérisque sont obligatoires.`
            : `Modifiez les informations de ce ${modelName.toLowerCase()} ci-dessous. Cliquez sur « Enregistrer » pour sauvegarder vos modifications.`;

        content.appendChild(title);
        content.appendChild(description);

        const badge = document.createElement('span');
        badge.className = 'form-hero-badge';
        badge.textContent = isAdd ? 'CRÉATION' : 'MODIFICATION';

        heroSection.appendChild(icon);
        heroSection.appendChild(content);
        heroSection.appendChild(badge);

        // Insérer le hero avant le formulaire
        const form = changeForm.querySelector('form');
        if (form) {
            form.parentNode.insertBefore(heroSection, form);
        }

        // Masquer les onglets Jazzmin
        const jazzyTabs = document.getElementById('jazzy-tabs');
        if (jazzyTabs) {
            jazzyTabs.style.display = 'none';
        }

        // Améliorer la disposition des fieldsets
        const fieldsets = changeForm.querySelectorAll('fieldset');
        fieldsets.forEach(function(fieldset) {
            // Appliquer la grille au contenu
            const cardBody = fieldset.querySelector('.card-body');
            if (cardBody && !fieldset.classList.contains('inline-group')) {
                cardBody.style.display = 'grid';
                cardBody.style.gap = '1rem';
                cardBody.style.gridTemplateColumns = 'repeat(2, minmax(0, 1fr))';
                cardBody.style.padding = '1.25rem';
            }
        });

        // Améliorer les champs individuels
        const formGroups = changeForm.querySelectorAll('.tab-content .form-group');
        formGroups.forEach(function(group, index) {
            // Appliquer le style de carte
            group.style.background = 'linear-gradient(135deg, var(--lb-surface) 0%, var(--lb-canvas) 100%)';
            group.style.border = '1.5px solid var(--lb-line)';
            group.style.borderRadius = 'var(--lb-radius)';
            group.style.boxShadow = 'var(--lb-shadow-sm)';
            group.style.margin = '0';
            group.style.minWidth = '0';
            group.style.padding = '.95rem 1.1rem';
            group.style.transition = 'all .2s cubic-bezier(0.4, 0, 0.2, 1)';
            
            // Animation en cascade
            group.style.animation = `fadeInUp 0.3s ease-out ${index * 0.05}s both`;

            // Focus effect
            group.addEventListener('focusin', function() {
                group.style.borderColor = 'var(--lb-gold)';
                group.style.boxShadow = 'var(--lb-shadow), 0 0 0 3px rgba(201, 155, 59, .18)';
                group.style.transform = 'translateY(-2px)';
            });

            group.addEventListener('focusout', function() {
                group.style.borderColor = 'var(--lb-line)';
                group.style.boxShadow = 'var(--lb-shadow-sm)';
                group.style.transform = 'translateY(0)';
            });

            // Améliorer les labels
            const label = group.querySelector('label');
            if (label) {
                label.style.color = 'var(--lb-wine)';
                label.style.display = 'block';
                label.style.float = 'none';
                label.style.fontSize = '.75rem';
                label.style.fontWeight = '800';
                label.style.letterSpacing = '.06em';
                label.style.margin = '0 0 .45rem';
                label.style.textTransform = 'uppercase';
                label.style.width = 'auto';
            }

            // Améliorer les inputs
            const inputs = group.querySelectorAll('input:not([type="checkbox"]):not([type="radio"]):not([type="file"]):not([type="range"]), select, textarea');
            inputs.forEach(function(input) {
                input.style.border = '1.5px solid var(--lb-line)';
                input.style.borderRadius = '10px';
                input.style.fontSize = '.95rem';
                input.style.minHeight = '48px';
                input.style.padding = '.6rem .9rem';
                input.style.transition = 'all .2s cubic-bezier(0.4, 0, 0.2, 1)';
                input.style.width = '100%';
                input.style.background = '#fff';
                input.style.boxShadow = '0 1px 3px rgba(0, 0, 0, .05)';

                input.addEventListener('focus', function() {
                    input.style.borderColor = 'var(--lb-gold)';
                    input.style.boxShadow = '0 0 0 3px rgba(201, 155, 59, .22), 0 4px 12px rgba(201, 155, 59, .1)';
                    input.style.transform = 'translateY(-1px)';
                });

                input.addEventListener('blur', function() {
                    input.style.borderColor = 'var(--lb-line)';
                    input.style.boxShadow = '0 1px 3px rgba(0, 0, 0, .05)';
                    input.style.transform = 'translateY(0)';
                });
            });

            // Champs en pleine largeur
            const fullWidthClasses = ['field-nom', 'field-title', 'field-name', 'field-first_name', 'field-last_name', 'field-email', 'field-telephone', 'field-description', 'field-content', 'field-notes', 'field-image', 'field-image_url'];
            fullWidthClasses.forEach(function(cls) {
                if (group.classList.contains(cls)) {
                    group.style.gridColumn = '1 / -1';
                }
            });
        });

        // Améliorer les boutons d'action
        const jazzyActions = document.getElementById('jazzy-actions');
        if (jazzyActions) {
            jazzyActions.style.marginTop = '.5rem';
            jazzyActions.style.position = 'sticky';
            jazzyActions.style.top = '1rem';

            const actionCard = jazzyActions.querySelector('.card');
            if (actionCard) {
                actionCard.style.border = '1.5px solid var(--lb-line)';
                actionCard.style.borderRadius = 'var(--lb-radius-lg)';
                actionCard.style.boxShadow = 'var(--lb-shadow)';
                actionCard.style.overflow = 'hidden';
            }

            const actionButtons = jazzyActions.querySelectorAll('.btn, input[type="submit"]');
            actionButtons.forEach(function(btn) {
                btn.style.alignItems = 'center';
                btn.style.borderRadius = '10px';
                btn.style.display = 'inline-flex';
                btn.style.fontSize = '.9rem';
                btn.style.fontWeight = '700';
                btn.style.gap = '.5rem';
                btn.style.justifyContent = 'center';
                btn.style.letterSpacing = '.01em';
                btn.style.minHeight = '50px';
                btn.style.minWidth = '150px';
                btn.style.padding = '.75rem 1.3rem';
                btn.style.transition = 'all .2s cubic-bezier(0.4, 0, 0.2, 1)';
                btn.style.width = '100%';
                btn.style.marginBottom = '.5rem';
            });

            // Bouton Enregistrer
            const saveBtn = jazzyActions.querySelector('[name="_save"]');
            if (saveBtn) {
                saveBtn.style.background = 'linear-gradient(115deg, var(--lb-wine) 0%, var(--lb-wine-600) 100%)';
                saveBtn.style.border = '1.5px solid var(--lb-wine)';
                saveBtn.style.boxShadow = '0 6px 18px rgba(100, 27, 44, .28)';
                saveBtn.style.color = '#fff';

                saveBtn.addEventListener('mouseenter', function() {
                    saveBtn.style.background = 'linear-gradient(115deg, var(--lb-wine-700) 0%, var(--lb-wine-800) 100%)';
                    saveBtn.style.borderColor = 'var(--lb-wine-800)';
                    saveBtn.style.boxShadow = '0 9px 24px rgba(100, 27, 44, .35)';
                    saveBtn.style.color = '#fff';
                    saveBtn.style.transform = 'translateY(-2px)';
                });

                saveBtn.addEventListener('mouseleave', function() {
                    saveBtn.style.background = 'linear-gradient(115deg, var(--lb-wine) 0%, var(--lb-wine-600) 100%)';
                    saveBtn.style.borderColor = 'var(--lb-wine)';
                    saveBtn.style.boxShadow = '0 6px 18px rgba(100, 27, 44, .28)';
                    saveBtn.style.color = '#fff';
                    saveBtn.style.transform = 'translateY(0)';
                });
            }

            // Bouton Enregistrer et ajouter
            const addAnotherBtn = jazzyActions.querySelector('[name="_addanother"]');
            if (addAnotherBtn) {
                addAnotherBtn.style.background = 'linear-gradient(135deg, var(--lb-gold-100) 0%, var(--lb-gold-200) 100%)';
                addAnotherBtn.style.border = '1.5px solid var(--lb-gold-200)';
                addAnotherBtn.style.color = 'var(--lb-gold-700)';

                addAnotherBtn.addEventListener('mouseenter', function() {
                    addAnotherBtn.style.background = 'linear-gradient(135deg, var(--lb-gold) 0%, var(--lb-gold-300) 100%)';
                    addAnotherBtn.style.borderColor = 'var(--lb-gold)';
                    addAnotherBtn.style.color = 'var(--lb-gold-800)';
                    addAnotherBtn.style.transform = 'translateY(-2px)';
                });

                addAnotherBtn.addEventListener('mouseleave', function() {
                    addAnotherBtn.style.background = 'linear-gradient(135deg, var(--lb-gold-100) 0%, var(--lb-gold-200) 100%)';
                    addAnotherBtn.style.borderColor = 'var(--lb-gold-200)';
                    addAnotherBtn.style.color = 'var(--lb-gold-700)';
                    addAnotherBtn.style.transform = 'translateY(0)';
                });
            }
        }

    });
})();
