from django.urls import path

from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('backup/<int:pk>/', views.BackupDetailView.as_view(), name='backup-detail'),
    path('backup/trigger/', views.TriggerBackupView.as_view(), name='backup-trigger'),
    path('backup/<int:pk>/download/', views.DownloadBackupView.as_view(), name='backup-download'),
    path('backup/<int:pk>/delete/', views.DeleteBackupView.as_view(), name='backup-delete'),
    path('config/', views.ConfigView.as_view(), name='config'),
    path('config/test/', views.TestConnectionView.as_view(), name='test-connection'),
]
