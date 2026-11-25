from django.views.generic import TemplateView

class HomeView(TemplateView):
    """Landing page view rendered after successful authentication."""
    template_name = "home.html"
