from django.urls import path, include
from django.contrib import admin


from . import views
#from .views import TargetDetailView, MainFunctionView

urlpatterns = [
	path("<int:pk>/",views.MainFunctionView.as_view(),name='query'),
	path('<int:pk>/', views.TargetDetailView.as_view(),name='detail')
]
