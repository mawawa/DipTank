
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('about/', views.about_view, name='about'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'), # Added logout URL
    path('error/', views.error_page_view, name='error_page'),
    path('dashboard/farmer/', views.dashboard_farmer_view, name='dashboard_farmer'),
    path('dashboard/officer/', views.dashboard_officer_view, name='dashboard_officer'),
]