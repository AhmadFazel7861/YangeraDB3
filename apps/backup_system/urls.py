from django.urls import path
from . import views

app_name = 'backups'

urlpatterns = [
    path('', views.backup_list, name='backup_list'),
    path('create/', views.create_backup, name='create_backup'),
    path('<uuid:pk>/download/', views.download_backup, name='download'),
    path('<uuid:pk>/restore/', views.restore_backup, name='restore'),
    path('<uuid:pk>/delete/', views.delete_backup, name='delete'),
    path('upload/', views.upload_restore, name='upload_restore'),
]