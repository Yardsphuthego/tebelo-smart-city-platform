from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from core.models import audit
from .forms import ProfileForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        audit(request=request, action="account.registered", obj=user)
        login(request, user)
        messages.success(request, "Your TEBELO account is ready.")
        return redirect("dashboard")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request=request, action="account.profile_updated", obj=request.user)
        messages.success(request, "Your preferences have been saved.")
        return redirect("profile")
    return render(request, "accounts/profile.html", {"form": form})
