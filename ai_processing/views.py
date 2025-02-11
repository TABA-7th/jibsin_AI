from django.shortcuts import render
from django.http import JsonResponse


# Create your views here.
def analysis(request):
    return JsonResponse({"test1": 23, "ddd":"ttt"})