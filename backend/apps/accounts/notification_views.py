import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserNotification
from apps.accounts.notifications import notifications_pour_utilisateur


@require_http_methods(['GET', 'POST'])
def notification_action(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'error': 'Accès refusé.'}, status=403)

    if request.method == 'GET':
        current = notifications_pour_utilisateur(request.user)
        response = JsonResponse({
            'success': True,
            'unread_count': sum(item['non_lue'] for item in current),
            'items': current,
        })
        response['Cache-Control'] = 'no-store'
        return response

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Requête invalide.'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'error': 'Requête invalide.'}, status=400)

    action = payload.get('action')
    key = payload.get('key')
    if not isinstance(action, str):
        return JsonResponse({'error': 'Action invalide.'}, status=400)
    visible = notifications_pour_utilisateur(request.user)

    if action == 'read_all':
        UserNotification.objects.filter(
            user=request.user,
            key__in=[item['key'] for item in visible],
        ).update(etat=UserNotification.Etat.LUE)
    elif action in {'read', 'unread', 'dismiss'} and isinstance(key, str):
        if key not in {item['key'] for item in visible}:
            return JsonResponse({'error': 'Notification introuvable.'}, status=404)
        etat = {
            'read': UserNotification.Etat.LUE,
            'unread': UserNotification.Etat.NON_LUE,
            'dismiss': UserNotification.Etat.MASQUEE,
        }[action]
        updated = UserNotification.objects.filter(user=request.user, key=key).update(etat=etat)
        if not updated:
            return JsonResponse({'error': 'Notification introuvable.'}, status=404)
    else:
        return JsonResponse({'error': 'Action invalide.'}, status=400)

    current = notifications_pour_utilisateur(request.user)
    response = JsonResponse({
        'success': True,
        'unread_count': sum(item['non_lue'] for item in current),
        'items': current,
    })
    response['Cache-Control'] = 'no-store'
    return response
