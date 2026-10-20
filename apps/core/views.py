from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def index(request):
    return render(request, 'core/index.html', {'active_tab': 'home'})