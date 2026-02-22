# home/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'api/tfbs', views.TFBSViewSet, basename='tfbs')
router.register(r'api/batch-tfbs', views.BatchTFBSViewSet, basename='batch-tfbs')

urlpatterns = [
    path('', views.index, name='index'),
    path('search/', views.search_results, name='search_results'),
    path('batch-search/', views.batch_search, name='batch_search'),
    path('batch-results/', views.batch_results, name='batch_results'),
    path('api/tfbs/download/', views.download_results, name='download_results'),
    path('api/batch-tfbs/download/', views.download_batch_results, name='download_batch_results'),
    path('tfbs-details/<int:pk>/', views.tfbs_details, name='tfbs_details'),
    path('evaluation-metrics/', views.evaluation_metrics, name='evaluation_metrics'),
    path('api/tf-names/', views.get_all_tf_names, name='get_all_tf_names'),
    path('api/cell-tissues/', views.get_all_cell_tissues, name='get_all_cell_tissues'),
    path('', include(router.urls)),
]