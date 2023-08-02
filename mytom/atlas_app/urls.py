from django.urls import path, include
from django.contrib import admin


from . import views

app_name = 'atlas_app'

urlpatterns = [
	path("<int:pk>/query/",views.QueryView.as_view(),name='query'),
	path('<int:pk>/', views.TargetDetailView.as_view(),name='detail'),
]
