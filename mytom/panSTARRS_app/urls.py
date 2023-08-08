from django.urls import path, include
from django.contrib import admin


from . import views

app_name = 'panSTARRS_app'

urlpatterns = [
	path("<int:pk>/panstarrsquery/",views.PanStarrsQueryView.as_view(),name='panstarrsquery'),
	path('<int:pk>/', views.TargetDetailView.as_view(),name='detail'),
]