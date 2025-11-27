from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .ml_engine import process_image_with_unet

@csrf_exempt # À retirer si vous utilisez des forms Django classiques avec token
def segment_image_view(request):
    if request.method == 'POST':
        # Vérifier si une image est présente
        if 'image' not in request.FILES:
            return JsonResponse({'error': 'Aucune image fournie'}, status=400)
            
        image_file = request.FILES['image']
        
        try:
            # Lire les bytes de l'image
            image_bytes = image_file.read()
            
            # Appel au moteur IA
            processed_image_io = process_image_with_unet(image_bytes)
            
            # Retourner l'image directement (Content-Type image/png)
            return HttpResponse(processed_image_io, content_type="image/png")
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Méthode non autorisée. Utilisez POST.'}, status=405)