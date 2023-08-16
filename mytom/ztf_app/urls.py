from django.urls import path, include
from django.contrib import admin


from . import views

app_name = 'ztf_app'

urlpatterns = [
	path('', views.DataProductUploadView.as_view(), name='upload'),
	path("<int:pk>/ztfquery/",views.ZTFQueryView.as_view(),name='ztfquery'),
	path('<int:pk>/', views.TargetDetailView.as_view(),name='detail'),
]
