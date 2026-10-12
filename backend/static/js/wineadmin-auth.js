/* WineAdmin — interactions des pages d'authentification :
   champs de code (OTP / 2FA) à saisie automatique, affichage du mot de passe,
   force du mot de passe, copie du secret TOTP.
 */
(function () {
  'use strict';

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? decodeURIComponent(m.pop()) : null;
  }
  window.setCookie = function (name, value, days) {
    var expires = '';
    if (days) {
      var d = new Date();
      d.setTime(d.getTime() + days * 864e5);
      expires = '; expires=' + d.toUTCString();
    }
    document.cookie = name + '=' + encodeURIComponent(value) + expires + '; path=/; SameSite=Lax';
  };

  /* ---------- Champs de code : auto-avance, collage, retour ---------- */
  document.querySelectorAll('.code-inputs, .lb-code').forEach(function (container) {
    var hidden = container.querySelector('input[name="code"][type="hidden"]');
    if (!hidden) {
      var form = container.closest('form');
      if (form) {
        hidden = form.querySelector('input[name="code"][type="hidden"]');
      }
    }
    var inputs = Array.prototype.filter.call(container.querySelectorAll('input'), function (i) {
      return i.type !== 'hidden';
    });

    function syncHidden() {
      if (hidden) {
        hidden.value = Array.prototype.map.call(inputs, function (i) { return i.value; }).join('');
      }
    }

    inputs.forEach(function (input, index) {
      input.addEventListener('input', function () {
        var val = input.value.replace(/[^0-9A-Za-z]/g, '').toUpperCase().slice(0, 1);
        input.value = val;
        if (val && index < inputs.length - 1) {
          inputs[index + 1].focus();
        }
        syncHidden();
      });
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' && !input.value && index > 0) {
          inputs[index - 1].focus();
        }
      });
      input.addEventListener('paste', function (e) {
        e.preventDefault();
        var paste = (e.clipboardData.getData('text') || '').replace(/[^0-9A-Za-z]/g, '').toUpperCase();
        for (var i = 0; i < inputs.length && i < paste.length; i++) {
          inputs[i].value = paste[i];
        }
        inputs[Math.min(paste.length, inputs.length - 1)].focus();
        syncHidden();
      });
    });
  });

  /* ---------- Afficher / masquer le mot de passe ---------- */
  document.querySelectorAll('.toggle-password').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var field = document.getElementById(btn.getAttribute('data-target')) ||
                  btn.closest('.password-wrap').querySelector('input');
      var visible = field.type === 'text';
      field.type = visible ? 'password' : 'text';
      btn.querySelector('i').className = visible ? 'fas fa-eye' : 'fas fa-eye-slash';
      field.focus();
    });
  });

  /* ---------- Force du mot de passe ---------- */
  var pwd = document.querySelector('[data-password-strength]');
  var meter = document.getElementById('password-meter');
  if (pwd && meter) {
    function strength(val) {
      var s = 0;
      if (val.length >= 8) { s++; }
      if (val.length >= 12) { s++; }
      if (/[a-z]/.test(val) && /[A-Z]/.test(val)) { s++; }
      if (/\d/.test(val)) { s++; }
      if (/[^A-Za-z0-9]/.test(val)) { s++; }
      return Math.min(5, s);
    }
    var labels = ['', 'Très faible', 'Faible', 'Moyen', 'Bon', 'Excellent'];
    pwd.addEventListener('input', function () {
      meter.removeAttribute('hidden');
      var s = strength(pwd.value);
      var pct = (s / 5) * 100;
      meter.querySelector('.meter-fill').style.width = pct + '%';
      meter.querySelector('.meter-label').textContent = pwd.value ? labels[s] : '';
      var hue = Math.round((s / 5) * 130);
      meter.querySelector('.meter-fill').style.background = 'hsl(' + hue + ', 60%, 40%)';
    });
  }

  /* ---------- Inscription : canal e-mail/SMS + état de chargement ---------- */
  var contactRadios = document.querySelectorAll('[data-contact-radio]');
  var contactFields = document.querySelectorAll('[data-contact]');
  function basculeCanal() {
    var checked = document.querySelector('[data-contact-radio]:checked');
    var type = checked ? checked.value : 'email';
    document.querySelectorAll('.lb-canal__option').forEach(function (opt) {
      opt.classList.toggle('is-checked', opt.querySelector('[data-contact-radio]').value === type);
    });
    contactFields.forEach(function (input) {
      var hint = document.querySelector('[data-hint="' + input.getAttribute('data-contact') + '"]');
      if (input.getAttribute('data-contact') === type) {
        input.setAttribute('required', '');
        if (hint) { hint.setAttribute('hidden', ''); }
      } else {
        input.removeAttribute('required');
        if (hint) { hint.removeAttribute('hidden'); }
      }
    });
  }
  contactRadios.forEach(function (radio) { radio.addEventListener('change', basculeCanal); });
  basculeCanal();

  var signupForm = document.querySelector('[data-signup-form]');
  if (signupForm) {
    signupForm.addEventListener('submit', function () {
      var btn = signupForm.querySelector('[data-signup-submit]');
      if (!btn || btn.disabled) { return; }
      var label = btn.querySelector('.label');
      var spinner = btn.querySelector('.spinner');
      if (label) { label.setAttribute('hidden', ''); }
      if (spinner) { spinner.removeAttribute('hidden'); }
      btn.classList.add('is-loading');
      btn.disabled = true;
    });
  }

  /* ---------- Copier le secret TOTP ---------- */
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy');
      var label = btn.querySelector('span');
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          label.textContent = 'Copié !';
          setTimeout(function () { label.textContent = 'Copier'; }, 1500);
        });
      }
    });
  });
})();